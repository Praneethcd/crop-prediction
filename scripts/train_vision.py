"""Fine-tune MobileNetV3 from train/val/test ImageFolder directories and export."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.remedies import classify_label


def main():
    import torch
    from torch import nn
    from torchvision import datasets,transforms,models
    parser=argparse.ArgumentParser()
    parser.add_argument('dataset',help='Directory containing train/, val/, test/ in ImageFolder format')
    parser.add_argument('--output',default='models/custom-vision')
    parser.add_argument('--epochs',type=int,default=10)
    parser.add_argument('--batch-size',type=int,default=32)
    args=parser.parse_args()
    if args.epochs<1 or args.batch_size<1:parser.error('epochs and batch-size must be positive')
    torch.manual_seed(42)
    tf=transforms.Compose([transforms.Resize(256),transforms.CenterCrop(224),transforms.ToTensor(),transforms.Normalize([.485,.456,.406],[.229,.224,.225])])
    training_tf=transforms.Compose([transforms.RandomResizedCrop(224),transforms.RandomHorizontalFlip(),transforms.ColorJitter(.1,.1,.1),transforms.ToTensor(),transforms.Normalize([.485,.456,.406],[.229,.224,.225])])
    sets={split:datasets.ImageFolder(Path(args.dataset)/split,transform=training_tf if split=='train' else tf) for split in ('train','val','test')}
    if any(s.class_to_idx!=sets['train'].class_to_idx for s in sets.values()):raise ValueError('Splits must have identical class names and order')
    labels=[classify_label(n) for n in sets['train'].classes]
    loaders={k:torch.utils.data.DataLoader(s,batch_size=args.batch_size,shuffle=k=='train',num_workers=0) for k,s in sets.items()}
    device=torch.device('mps' if torch.backends.mps.is_available() else 'cuda' if torch.cuda.is_available() else 'cpu')
    model=models.mobilenet_v3_small(weights=models.MobileNet_V3_Small_Weights.DEFAULT)
    model.classifier[3]=nn.Linear(model.classifier[3].in_features,len(labels));model.to(device)
    optimizer=torch.optim.AdamW(model.parameters(),lr=3e-4);loss_fn=nn.CrossEntropyLoss()
    root=Path(args.output);root.mkdir(parents=True,exist_ok=True)
    best=-1;history=[]
    def evaluate(loader):
        model.eval();correct=count=0
        with torch.inference_mode():
            for x,y in loader:
                predictions=model(x.to(device)).argmax(1).cpu();correct+=int((predictions==y).sum());count+=len(y)
        return correct/count
    for epoch in range(args.epochs):
        model.train()
        for x,y in loaders['train']:
            optimizer.zero_grad();loss=loss_fn(model(x.to(device)),y.to(device));loss.backward();optimizer.step()
        accuracy=evaluate(loaders['val']);history.append({'epoch':epoch+1,'validation_accuracy':accuracy})
        print(history[-1],flush=True)
        if accuracy>best:
            best=accuracy;torch.save(model.state_dict(),root/'best_weights.pt')
    model.load_state_dict(torch.load(root/'best_weights.pt',map_location=device,weights_only=True))
    test_accuracy=evaluate(loaders['test']);model.cpu().eval()
    path=root/'model_scripted.pt';torch.jit.script(model).save(str(path))
    metadata={'version':'custom-mobilenet-v3','image_size':224,'resize_size':256,'classes':labels,
              'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'temperature':1}
    (root/'metadata.json').write_text(json.dumps(metadata,indent=2))
    (root/'training_report.json').write_text(json.dumps({'history':history,'test_accuracy':test_accuracy,
       'split_sizes':{k:len(s) for k,s in sets.items()},'note':'Dataset splits must be grouped by plant/source to avoid leakage. Field-image calibration remains required.'},indent=2))
    print('Exported',path,'test accuracy',test_accuracy)


if __name__=='__main__':main()
