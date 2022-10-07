import os

from noq_form.config.models import AccountConfig, Config
from noq_form.core.utils import yaml

demo_config = Config(
    accounts=[
        AccountConfig(
            account_id="759357822767", account_name="Development", aws_profile="noq_dev"
        ),
        AccountConfig(
            account_id="259868150464", account_name="Staging", aws_profile="noq_staging"
        ),
        AccountConfig(
            account_id="940552945933", account_name="Production", aws_profile="noq_prod"
        ),
    ]
)

with open(os.path.join(os.path.dirname(__file__), "config.yaml"), "w") as f:
    f.write(yaml.dump(demo_config.dict(exclude_none=True, exclude_unset=True)))
