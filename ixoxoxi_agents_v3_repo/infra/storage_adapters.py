class BlobStorageAdapter:
    """
    Azure Blob Storage adapter (scaffold).
    """
    def __init__(self, connection_string=None):
        self.connection_string = connection_string

    def upload(self, container, blob_name, data: bytes):
        raise NotImplementedError("Implement Azure Blob upload")

    def download(self, container, blob_name):
        raise NotImplementedError("Implement Azure Blob download")


class S3StorageAdapter:
    """
    AWS S3 adapter (scaffold).
    """
    def __init__(self, aws_key=None, aws_secret=None, region=None):
        self.aws_key = aws_key
        self.aws_secret = aws_secret
        self.region = region

    def upload(self, bucket, key, data: bytes):
        raise NotImplementedError("Implement S3 upload")

    def download(self, bucket, key):
        raise NotImplementedError("Implement S3 download")
