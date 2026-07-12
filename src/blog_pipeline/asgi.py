from blog_pipeline.app import create_app
from blog_pipeline.config import load_settings
from blog_pipeline.logging_setup import setup_logging

setup_logging()
app = create_app(load_settings())
