import os
from pathlib import Path

import torch
from torchvision import transforms
import celery
import sys

sys.path.append(str(Path(__file__).resolve().parent / "unsupervised_classification"))
from utils.common_config import get_model, get_val_transformations
from utils.config import create_config


class ClassificationTask(celery.Task):

    def __init__(self):
        sys.path.append(str(Path(__file__).resolve().parent))
        self.config = {
            'model_config_path': os.environ.get('CLASSIFICATION_CONFIG_PATH', None),
            'device_id': int(os.environ.get('CLASSIFICATION_DEVICE', -1))
        }
        print(self.config)
        assert self.config['model_config_path'] is not None, "You must supply a path to a model configuration in the " \
                                                             "environment variable CLASSIFICATION_CONFIG_PATH "

        self.idx_to_label_map = {
            0: "Auction catalogue",
            1: "Book of Hours",
            2: "Book",
            3: "Legal",
            4: "Newspaper",
            5: "Other",
            6: "Photography"
        }

        self.document_classifier = None
        self.transforms = None

    def initialize(self):
        if self.document_classifier is not None:
            return

        config_path = Path(self.config['model_config_path'])
        config_env = config_path / "env.yml"
        config_exp = config_path / "config.yml"
        tb_run = ""  # Not needed
        model_checkpoint = config_path / "model.pth.tar"

        p = create_config(config_env, config_exp, tb_run, make_dirs=False)
        torch.backends.cudnn.benchmark = True

        model = get_model(p)
        checkpoint = torch.load(model_checkpoint, map_location='cpu')
        model.load_state_dict(checkpoint['model'])

        model = torch.nn.DataParallel(model)
        model = model.cuda()
        model.eval()

        self.transforms = transforms.Compose([transforms.Resize(240), get_val_transformations(p)])
        self.document_classifier = model

    def predict(self, image):
        transformed_image = self.transforms(image)
        probs = self.document_classifier(transformed_image.unsqueeze(0))
        probs = probs[0].squeeze()

        predicted_class = torch.argmax(probs).item()

        result = {
            "predicted_class": self.idx_to_label_map[predicted_class],
            "confidence": probs[predicted_class].item()
        }

        return result
