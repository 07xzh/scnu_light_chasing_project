class BasePipeline:
    """All recognition pipelines inherit from this."""
    name: str = "base"

    def load(self):
        """Load model weights. Called once on startup."""
        pass

    def process(self, image):
        """Process a frame. Returns dict or None."""
        raise NotImplementedError
