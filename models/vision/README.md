---
license: mit
tags:
  - image-classification
  - agriculture
  - plant-disease
  - mobilenet
  - pytorch
  - onnx
datasets:
  - emmarex/plantdisease
metrics:
  - accuracy
library_name: pytorch
pipeline_tag: image-classification
---

# ConCaPlant — PlantVillage Crop Disease Classifier

A lightweight image classifier fine-tuned on the [PlantVillage dataset](https://www.kaggle.com/datasets/emmarex/plantdisease)
to detect crop leaf diseases across 15 classes.

## Model Details

- **Architecture:** ConCaPlant (1.53M parameters), ImageNet-pretrained backbone, fine-tuned classifier head
- **Input:** RGB image, resized/cropped to {256}x{256}, normalized with ImageNet mean/std
- **Output:** Logits over 15 disease/healthy classes (see `class_names.json`)
- **Test accuracy:** 0.9977382875605816
- **Best validation accuracy:** 0.997092084006462
- **Framework:** PyTorch (state_dict + TorchScript + ONNX exports included)

## Files

| File | Purpose |
|---|---|
| `pytorch_model.bin` | Raw `state_dict`, load into the same architecture in PyTorch |
| `model_scripted.pt` | TorchScript export, no class definition needed to load |
| `model.onnx` | ONNX export for cross-framework / edge inference |
| `class_names.json` | Ordered list mapping output index -> class label |
| `training_config.json` | Hyperparameters and run metadata |

## Intended Use

Assistive screening of crop leaf photos for common diseases (e.g. blight, mildew, mosaic virus, bacterial spot)
across tomato, potato, pepper, and other crops covered by PlantVillage. Intended for research, education, and as a
component in decision-support tools — **not** a substitute for expert agronomic diagnosis, especially for
high-stakes treatment decisions.

## How to Use (PyTorch)

```python
import torch, json
from torchvision import transforms, models
from PIL import Image

# Rebuild architecture matching training, then load weights
model = models.{MODEL_NAME}(weights=None)
# NOTE: if using mobilenet_v3, replace classifier[3] to match num_classes before loading:
# model.classifier[3] = torch.nn.Linear(model.classifier[3].in_features, {num_classes})
state_dict = torch.load("pytorch_model.bin", map_location="cpu")
model.load_state_dict(state_dict)
model.eval()

class_names = json.load(open("class_names.json"))

tfms = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop({img_size}),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])

img = Image.open("leaf.jpg").convert("RGB")
x = tfms(img).unsqueeze(0)

with torch.no_grad():
    logits = model(x)
    pred = logits.argmax(dim=1).item()

print(class_names[pred])
```

## How to Use (ONNX Runtime)

```python
import onnxruntime as ort
import numpy as np
from PIL import Image
from torchvision import transforms
import json

sess = ort.InferenceSession("model.onnx")
class_names = json.load(open("class_names.json"))

tfms = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop({img_size}),
    transforms.ToTensor(),
    transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
])

img = Image.open("leaf.jpg").convert("RGB")
x = tfms(img).unsqueeze(0).numpy()

logits = sess.run(None, {"input": x})[0]
pred = int(np.argmax(logits, axis=1)[0])
print(class_names[pred])
```

## Training Data

[PlantVillage dataset](https://www.kaggle.com/datasets/emmarex/plantdisease) — labeled leaf images across multiple
crop species and disease categories. Split 70/15/15 train/val/test for this run.

## Limitations & Biases

- Trained on lab-condition/curated leaf photos (uniform backgrounds); accuracy may be lower on field photos with
  variable lighting, backgrounds, occlusion, or co-occurring diseases.
- Class distribution in PlantVillage is imbalanced across crops/diseases — check `training_config.json` and the
  per-class F1 scores from the notebook before relying on this model for underrepresented classes.
- Not validated for crops or diseases outside the PlantVillage label set.

## Citation

If you use this model, please cite the PlantVillage dataset and this repository.
