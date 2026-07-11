from blog_pipeline.app import create_app
from blog_pipeline.config import load_settings

app = create_app(load_settings())
