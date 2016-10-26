#!/usr/bin/python
import hashlib
import subprocess
import traceback
from tempfile import NamedTemporaryFile

from google.cloud import speech, storage
from google.cloud.exceptions import Forbidden, NotFound
from google.cloud.storage import Blob

BUCKET_NAME = 'freelawproject-test'
PATH = "michael_queen_v._ed_schultz_cl.mp3"
SVC_PATH = '/home/mlissner/Encryption Keys/gcloud/CourtListener Development-37abbe45fa8d.json'


def reencode_file(path):
    """Reencode the file as LINEAR16 format"""
    with NamedTemporaryFile(prefix='transcode_', suffix='.raw') as tmp:
        # From: https://cloud.google.com/speech/support#troubleshooting:
        # "The LINEAR16 encoding must be 16-bits, signed-integer,
        # little-endian."
        # In avconv, this translates to "s16le". See also:
        # http://stackoverflow.com/a/4854627/64911 and
        # https://trac.ffmpeg.org/wiki/audio%20types
        avconv_command = ['avconv', '-i', path, '-f', 's16le', tmp.name]
        try:
            _ = subprocess.check_output(
                avconv_command,
                stderr=subprocess.STDOUT,
            )
        except subprocess.CalledProcessError, e:
            print('avconv failed command: %s\n'
                  'error code: %s\n'
                  'output: %s\n' % (avconv_command, e.returncode, e.output))
            print traceback.format_exc()


def upload_item(path):
    # Set up the client
    client = storage.Client.from_service_account_json(
        SVC_PATH, project='courtlistener-development')

    # Check that the bucket exists
    try:
        b = client.get_bucket(BUCKET_NAME)
    except Forbidden as e:
        print("Received Forbidden (403) error while getting bucket. This could "
              "mean that you do not have billing set up for this "
              "account/project, or that somebody else has taken this bucket "
              "from the global namespace.")
        raise e
    except NotFound:
        print("Bucket wasn't found. Creating the bucket.")
        b.lifecycle_rules = [{
            'action': {'type': 'Delete'},
            'condition': {'age': 7},
        }]
        b.create()
        b.make_public(future=True)

    # Name it after a SHA2 hash of the item, so that we don't have collisions.
    with open(path, 'rb') as f:
        file_name = 'transcripts-%s' % hashlib.sha256(f.read()).hexdigest()
        blob = Blob(file_name, b)
        blob.upload_from_file(f, rewind=True)


def do_speech_to_text():
    """Convert the file to text"""
    client = speech.Client.from_service_account_json(
        SVC_PATH, project='courtlistener-development')
    operation = client.async_recognize(

    )
    pass


def poll_and_save():
    """Poll for the finished result and save the data (mock it here)"""
    pass


def delete_item(obj_name):
    # Items will have a one week lifetime if we do nothing, but the sooner we
    # delete an item, the less money we'll spend.
    blob = Blob(obj_name, BUCKET_NAME)
    blob.delete()

    # TODO: Delete the tmp file as well.



if __name__ == '__main__':
    upload_item(PATH)
