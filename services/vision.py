"""Private CPU inference using a pinned, actually trained MobileNetV3 artifact."""
import hashlib
import json
import os
from functools import lru_cache
from pathlib import Path
import numpy as np
from services.remedies import canonical_crop, classify_label, recommendations

DEFAULT_ROOT=Path(__file__).resolve().parents[1]/'models'/'vision'


@lru_cache(maxsize=1)
def load_model():
    import torch
    root=DEFAULT_ROOT
    path=Path(os.getenv('DISEASE_MODEL_PATH',str(root/'model_scripted.pt')))
    metadata_path=Path(os.getenv('DISEASE_LABELS_PATH',str(root/'metadata.json')))
    try:
        metadata=json.loads(metadata_path.read_text())
        if metadata.get('sha256') and hashlib.sha256(path.read_bytes()).hexdigest()!=metadata['sha256']:
            raise RuntimeError('Model checksum mismatch')
        model=torch.jit.load(str(path),map_location='cpu').eval()
    except (OSError,ValueError) as exc:
        raise RuntimeError('Trained artifact missing or invalid; run python scripts/setup_vision.py') from exc
    if not isinstance(metadata.get('classes'),list) or not metadata['classes']:
        raise RuntimeError('Model metadata must include ordered classes')
    torch.set_num_threads(min(4,os.cpu_count() or 1))
    return model,metadata


def predict(image,crop,state='',language='en'):
    import torch
    from torchvision import transforms
    crop=canonical_crop(crop)
    model,metadata=load_model()
    classes=metadata['classes']
    if crop not in {r['crop'] for r in classes}:
        raise ValueError('This model supports Tomato, Potato and Pepper. Select a supported crop lot.')
    if min(image.size)<64:raise ValueError('Use a crop photo of at least 64 × 64 pixels')
    small=np.asarray(image.resize((64,64)),dtype=np.float32)
    if float(small.std(axis=(0,1)).mean())<5:
        raise ValueError('Image has too little detail; photograph a well-lit leaf against a clear background')
    transform=transforms.Compose([transforms.Resize(metadata.get('resize_size',256)),
        transforms.CenterCrop(metadata.get('image_size',224)),transforms.ToTensor(),
        transforms.Normalize(metadata.get('mean',[.485,.456,.406]),metadata.get('std',[.229,.224,.225]))])
    with torch.inference_mode():
        logits=model(transform(image).unsqueeze(0))
        if tuple(logits.shape)!=(1,len(classes)) or not torch.isfinite(logits).all():
            raise RuntimeError('Model output does not match metadata')
        probs=torch.softmax(logits/metadata.get('temperature',1),dim=1)[0]
    index=int(probs.argmax());label=classes[index];confidence=float(probs[index])
    if label['crop']!=crop:raise ValueError(f"Photo appears to be {label['crop']}, not {crop}. Retake or select the correct lot.")
    top=probs.topk(min(3,len(classes)))
    return {**label,'confidence':confidence,'model_version':metadata['version'],
            'needs_review':confidence<.9,'storage_risk_inferred':label['severity']=='severe' and confidence>=.9,
            'top_predictions':[{'label':classes[int(i)]['label'],'confidence':float(p)} for p,i in zip(top.values,top.indices)],
            'model_limitations':'Trained on curated leaf images. Not validated on harvested products or arbitrary/non-leaf images. Softmax confidence is not calibrated diagnostic certainty.',
            'remedies':recommendations(label,state,language)}
