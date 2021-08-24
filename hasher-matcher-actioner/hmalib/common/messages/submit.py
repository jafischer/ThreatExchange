# Copyright (c) Facebook, Inc. and its affiliates. All Rights Reserved

from urllib.parse import unquote_plus
import typing as t
from dataclasses import dataclass

from threatexchange.content_type.content_base import ContentType

from hmalib.common.content_sources import S3BucketContentSource
from hmalib.common.logging import get_logger


logger = get_logger(__name__)


@dataclass
class URLSubmissionMessage:
    """
    Content has been submitted using a URL. Used by submission API lambda and
    hasher lambdas to communicate via SNS / SQS.

    Includes the type of content as threatexchange ContentTypes. Used to
    identify the signals to be generated for content.
    """

    content_type: t.Type[ContentType]
    content_id: str

    url: str

    # Used to distinguish these messages from S3 Upload events. Leave it alone
    # if you don't know what you are doing.
    event_type: str = "URLSubmission"

    def to_sqs_message(self) -> dict:
        return {
            "ContentType": self.content_type.get_name(),
            "ContentId": self.content_id,
            "URL": self.url,
            "EventType": self.event_type,
        }

    @classmethod
    def from_sqs_message(cls, d: dict) -> "URLSubmissionMessage":
        return cls(
            content_type=d["ContentType"],
            content_id=d["ContentId"],
            url=d["URL"],
            event_type=d["EventType"],
        )

    @classmethod
    def could_be(cls, d: dict) -> bool:
        """
        Convenience method. Returns True if `d` can be converted to a
        URLImageSubmissionMessage.
        """
        return "EventType" in d


@dataclass
class S3ImageSubmission:
    """
    S3 -> SNS batches events together. This represents one of the events. An
    `S3ImageSubmissionBatchMessage` event is emitted. Each batch has one or more
    of these objects.
    """

    content_id: str
    bucket: str
    key: str


@dataclass
class S3ImageSubmissionBatchMessage:
    """
    An image has been uploaded to S3 from the Submission API. An autogenerated
    event has been emitted by S3 to SNS. This converts that into a set of
    messages each representing one image and its content id based on convention
    used by the submission lambda.

    eg. If the s3 path structure convention were to change, you'd make changes
    in the submission API and here, but not need to make changes in any of the
    hasher lambdas.
    """

    image_submissions: t.List[S3ImageSubmission]

    @classmethod
    def from_sqs_message(
        cls, d: dict, image_prefix: str
    ) -> "S3ImageSubmissionBatchMessage":
        result = []

        for s3_record in d["Records"]:
            bucket_name = s3_record["s3"]["bucket"]["name"]
            key = unquote_plus(s3_record["s3"]["object"]["key"])

            # Ignore Folders and Empty Files
            if s3_record["s3"]["object"]["size"] == 0:
                logger.info("Disregarding empty file or directory: %s", key)
                continue

            content_id = S3BucketContentSource.get_content_id_from_s3_key(
                key, image_prefix
            )
            result.append(S3ImageSubmission(content_id, bucket_name, key))

        return cls(image_submissions=result)

    @classmethod
    def could_be(cls, d: dict) -> bool:
        """
        Convenience mthod. Returns true if `d` can be converted to an
        S3ImageSubmissionBatchMessage.
        """
        return "Records" in d and len(d["Records"]) > 0 and "s3" in d["Records"][0]
