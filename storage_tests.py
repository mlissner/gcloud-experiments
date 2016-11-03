#!/usr/bin/python
import hashlib
import json
import subprocess
import time
import traceback
from tempfile import NamedTemporaryFile

import httplib2
from google.cloud import storage
from google.cloud.exceptions import Forbidden, NotFound
from google.cloud.storage import Blob
from googleapiclient import discovery
from oauth2client.client import GoogleCredentials

BUCKET_NAME = 'freelawproject-test'
PATH = "michael_queen_v._ed_schultz_cl.mp3"
SVC_PATH = '/home/mlissner/Encryption Keys/gcloud/CourtListener Development-37abbe45fa8d.json'


def encode_as_linear16(path, tmp):
    # From: https://cloud.google.com/speech/support#troubleshooting:
    # "The LINEAR16 encoding must be 16-bits, signed-integer,
    # little-endian."
    # In avconv, this translates to "s16le". See also:
    # http://stackoverflow.com/a/4854627/64911 and
    # https://trac.ffmpeg.org/wiki/audio%20types
    print("Re-encoding the file as raw file.")
    avconv_command = [
        'avconv',
        '-y',           # Assume yes (clobber existing files)
        '-i', path,     # Input file
        '-f', 's16le',  # Force output format
        '-ac', '1',     # Mono
        '-ar', '16k',   # Sample rate of 16000Mhz
        tmp.name,       # Output file
    ]
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
        raise e


def upload_item_as_raw_file(path):
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

    with NamedTemporaryFile(prefix='transcode_', suffix='.raw') as tmp:
        encode_as_linear16(path, tmp)

        # Name it after a SHA2 hash of the item, to avoid collisions.
        file_name = 'transcripts-%s' % hashlib.sha256(tmp.read()).hexdigest()
        print("Uploading: %s to bucket: %s" % (file_name, b.name))
        blob = Blob(file_name, b)
        blob.upload_from_file(tmp, rewind=True)

    return blob


def get_speech_service():
    """Make a speech service that we can use to make requests."""
    credentials = GoogleCredentials.from_stream(SVC_PATH).create_scoped(
        ['https://www.googleapis.com/auth/cloud-platform'])
    http = httplib2.Http()
    credentials.authorize(http)
    return discovery.build('speech', 'v1beta1', http=http)


def do_speech_to_text(blob):
    """Convert the file to text"""
    service = get_speech_service()
    print("Running STT...")
    response = service.speech().asyncrecognize(
        body={
            'config': {
                'encoding': 'LINEAR16',
                'sampleRate': 16000,
                'maxAlternatives': 10,
                'speechContext': {'phrases': ['remand']},
            },
            'audio': {
                'uri': 'gs://%s/%s' % (blob.bucket.name, blob.name),
            }
        }).execute()

    #   5,  10,   20,   40,   80 minutes
    # 300, 600, 1200, 2400, 4800 seconds
    delay = 5
    #delay = 300
    operation_name = response['name']
    polling_request = service.operations().get(name=operation_name)
    print("Polling for completion...")
    while delay <= 4800:
        time.sleep(delay)
        polling_response = polling_request.execute()
        if 'done' in polling_response and polling_response['done']:
            print "  STT complete!"
            print json.dumps(polling_response['response'], indent=2)
            break
        else:
            print "  Didn't get it in %s seconds..." % delay
            delay *= 2
    else:
        # Fell out of while loop w/o getting results. Handle failure.
        pass

    # TODO: Save results to database, etc. here.
    return blob, polling_response


def delete_item(blob):
    # Items will have a one week lifetime if we do nothing, but the sooner we
    # delete an item, the less money we'll spend.
    print("Deleting the blob at: %s" % blob.name)
    blob.delete()


if __name__ == '__main__':
    blob = upload_item_as_raw_file('estate_of_leon_brackens_v._loisville_jefferson_county_cl.mp3')
    blob = do_speech_to_text(blob)
    delete_item(blob)
