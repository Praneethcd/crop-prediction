"""Reproducibly install the MIT-licensed trained MobileNetV3 model, not random weights."""
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from services.remedies import classify_label

REPO='imaflower/plantvillage-mobilenetv3'
REVISION='d76fe187be1c4c3a5474f835a7a70cd08c7ab085'


def main():
    from huggingface_hub import hf_hub_download
    root=Path(__file__).resolve().parents[1]/'models'/'vision';root.mkdir(parents=True,exist_ok=True)
    for name in ('model_scripted.pt','class_names.json','training_config.json','README.md'):
        hf_hub_download(REPO,name,revision=REVISION,local_dir=root)
    config=json.loads((root/'training_config.json').read_text())
    names=json.loads((root/'class_names.json').read_text())
    metadata={'version':'plantvillage-mobilenetv3-'+REVISION[:12],
              'architecture':config['model_name'],'source':'https://huggingface.co/'+REPO,
              'revision':REVISION,'license':'MIT','image_size':config['img_size'],'resize_size':256,
              'mean':config['normalize_mean'],'std':config['normalize_std'],
              'sha256':hashlib.sha256((root/'model_scripted.pt').read_bytes()).hexdigest(),
              'classes':[classify_label(n) for n in names]}
    (root/'metadata.json').write_text(json.dumps(metadata,indent=2))
    print('Installed trained model:',metadata['version'],'with',len(names),'classes')


if __name__=='__main__':main()
