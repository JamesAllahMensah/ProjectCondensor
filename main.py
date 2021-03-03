import hashlib
import time
import urllib

import boto3
from botocore.exceptions import ClientError
import json
import logging
import glob, os
import pathlib


# Author: James (Jimmy) Allah-Mensah
# Date: 2/25/21
# Version: Python 3.7

# Calculates the s3 etag (hash) of the audio file and compares to that of those already in the S3 bucket
def calculate_s3_etag(file_path, chunk_size=8 * 1024 * 1024):
    md5s = []

    with open(file_path, 'rb') as fp:
        while True:
            data = fp.read(chunk_size)
            if not data:
                break
            md5s.append(hashlib.md5(data))

    if len(md5s) < 1:
        return '"{}"'.format(hashlib.md5().hexdigest())

    if len(md5s) == 1:
        return '"{}"'.format(md5s[0].hexdigest())

    digests = b''.join(m.digest() for m in md5s)
    digests_md5 = hashlib.md5(digests)
    return '"{}-{}"'.format(digests_md5.hexdigest(), len(md5s))


# Searches for a .mp4 within the script directory
def retrieve_audio():
    print('Retrieving Audio File(s)...')
    output_file = ''
    audio_files = []
    file_path = pathlib.Path(__file__).parent.absolute()
    os.chdir(file_path)
    for file in glob.glob("*.mp4"):
        audio_files.append(file)

    if len(audio_files) == 0:
        print('No .mp4 files were found. Please ensure that they are located in {}'.format(file_path))
        return None

    elif len(audio_files) == 1:
        return audio_files[0]
    else:
        correct_file = input('{} .mp4 files were found. Please enter the name of the desired audio file: (Enter L to list all .mp4 files):'.format(len(audio_files)))
        if correct_file.lower()[0] == 'l':
            for idx, val in enumerate(audio_files):
                print('{}: {}'.format(idx+1, val))

            selected_file = input('Please enter the file index (ex: 1) or the file name of the desired file (ex: {}):'.format(audio_files[0]))
            if selected_file.isnumeric():
                while int(selected_file) > len(audio_files) or int(selected_file) > 0 :
                    selected_file = input(
                        'Please enter the file index (ex: 1) or the file name of the desired file (ex: {}):'.format(
                            audio_files[0]))
                return audio_files[int(selected_file) - 1]
            else:
                while selected_file.lower() not in map(lambda x:x.lower(),audio_files) and selected_file.lower() not in map(lambda x:x.lower().replace(".mp4",""),audio_files):
                    selected_file = input(
                        'Could not find that file. Please re-enter the file index (ex: 1) or the file name of the desired file (ex: {}):'.format(
                            audio_files[0]))

                output_file = selected_file
        else:
            while correct_file.lower() not in map(lambda x: x.lower(), audio_files) and correct_file.lower() not in map(lambda x:x.lower().replace(".mp4",""),audio_files):
                correct_file = input(
                    'Could not find that file. Please re-enter the file index (ex: 1) or the file name of the desired file (ex: {}):'.format(
                        audio_files[0]))

            output_file = correct_file


        if output_file not in audio_files:
            for audio_file in audio_files:
                if '.mp4' not in output_file:
                    if (output_file.lower() + '.mp4') == audio_file.lower():
                        return audio_file
                else:
                    if output_file.lower() == audio_file.lower():
                        return audio_file



# Uploads the local file into the S3 bucket and returns the file URI
def upload_file(file_name, bucket, object_name=None):
    if object_name is None:
        object_name = file_name

    if file_name is None:
        return None

    s3_client = boto3.client('s3')

    try:
        print('Uplading file to S3 Bucket...')
        for bucket_file in s3_client.list_objects(Bucket=bucket)['Contents']:
            if file_name == bucket_file['Key'] or calculate_s3_etag(file_name) == bucket_file['ETag']:
                error_msg = input('File: {} already exists\nWould you like to overwrite this file (Y/N):'.format(file_name))
                if error_msg.lower()[0] == 'y':
                    s3_client.delete_object(Bucket=bucket, Key=bucket_file['Key'])
                    print('File successfully overwritten.')
                else:
                    return None

        s3_client.upload_file(file_name, bucket, object_name)
        file_path = ('s3://{}/' + file_name).format(bucket)
    except ClientError as e:
        logging.error(e)
        return None
    return file_path


# Returns the name of an available S3 Bucket
def get_s3_bucket(preference):
    print('Retrieving S3 Bucket Information...')
    s3 = boto3.client('s3')
    bucket_list = s3.list_buckets()['Buckets']
    if len(bucket_list) == 1:
        return bucket_list[0]['Name']
    else:
        if preference is None:
            return bucket_list[0]['Name']
        else:
            for bucket in bucket_list:
                if bucket['Name'].lower() == preference.lower():
                    return bucket['Name']
                else:
                    return bucket_list[0]['Name']



# Checks if the job name already exists
def is_job_name_unique(job_name):
    s3_client = boto3.client('transcribe')
    transcription_jobs = s3_client.list_transcription_jobs()['TranscriptionJobSummaries']
    for job in transcription_jobs:
        if job['TranscriptionJobName'] == job_name and job['TranscriptionJobStatus'] == 'COMPLETED':
            return False

    return True


# Starts the transcription job and returns a json file when complete
def transcribe_file(file_uri, transcribe_client, job_name):
    if file_uri is None:
        return file_uri

    if not is_job_name_unique(job_name):
        error_msg = input('Job Name: {} already exists. \nDo you want to override the existed job (Y/N):'.format(job_name))
        if error_msg.lower()[0] == 'y':
            job_name = input('Please enter a transcription job name:')
            while not is_job_name_unique(job_name):
                job_name = input('Job Name: {} already exists. Please enter a new transcription job name:'.format(job_name))
        else:
            return None

    transcribe_client.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={'MediaFileUri': file_uri},
        MediaFormat='mp4',
        LanguageCode='en-US',
        Settings={
            'ShowSpeakerLabels': True,
            'MaxSpeakerLabels': 10
        }
    )

    max_tries = 60
    while max_tries > 0:
        max_tries -= 1
        job = transcribe_client.get_transcription_job(TranscriptionJobName=job_name)
        job_status = job['TranscriptionJob']['TranscriptionJobStatus']
        if job_status in ['COMPLETED', 'FAILED']:
            print(f"Job {job_name} is {job_status}.")
            if job_status == 'COMPLETED':
                print(
                    f"Download the transcript from\n"
                    f"\t{job['TranscriptionJob']['Transcript']['TranscriptFileUri']}.")

            return str(job['TranscriptionJob']['Transcript']['TranscriptFileUri'])
        else:
            print(f"Waiting for {job_name}. Current status is {job_status}.")
        time.sleep(10)
    return None


# Parses the JSON file into an easy to follow format, identify speakers
def correlate_speakers(transcription_response):
    if transcription_response is None:
        return None

    print('Identifying the speakers and formatting text...')
    if transcription_response is not None:
        response = urllib.request.urlopen(transcription_response)
        data = json.loads(response.read())

        transcript = data['results']['transcripts'][0]['transcript']
        word_list = transcript.split()
        counter = 0
        full_transcription = []

        for segment in data['results']['speaker_labels']['segments']:
            num_words = len(segment['items'])
            speaker = segment['speaker_label'].replace("spk_", "Speaker ")
            speaker = speaker.split(" ")[0] + " " + str(int(speaker[len(speaker) - 1]) + 1) + ":"
            segment_text = word_list[counter:counter + num_words]

            script = ''
            for x in segment_text:
                script += x + ' '
            full_transcription.append((speaker, script.rstrip()))
            counter = counter + num_words

        for i in full_transcription:
            print(i[0])
            print(i[1] + "\n")
        return full_transcription


# Writes the formatted transcription to a text file
def output_transcription(transcribed_data):
    if transcribed_data is None:
        return False

    print('Printing the output to a text file...')
    f = open("Output.txt", "w")
    for i in transcribed_data:
        f.write(i[0] + "\n")
        f.write(i[1] + "\n")
        f.write("\n")
    f.close()
    print('Transcription Complete!')
    return True


# Deletes the audio file from the S3 bucket & the transcription job
def reserve_space(job_name, object_key, bucket):
    reserve = input('Would you like to delete the transcription job and audio file to reserve space (Y/N):')
    if reserve.lower()[0] == 'y':
        try:
            s3_client = boto3.client('s3')
            s3_client.delete_object(Bucket=bucket, Key=object_key)
            s3_client.delete_transcription_job(job_name)
            print('Job {} & File {} have successfully been deleted.'.format(job_name, object_key))
        except ClientError as e:
            logging.error(e)


def main():
    # Loads AWS S3 bucket information, with preference option
    s3_bucket_name = get_s3_bucket(None)

    # Searches for a .mp4 within the script directory
    file_name = retrieve_audio()

    # 1. Upload file to AWS S3 Bucket
    file_uri = upload_file(file_name, s3_bucket_name)

    # 2. Create the Transcription Job
    job_name = input('Please enter a transcription job name:').replace(" ","_")
    transcribe_client = boto3.client('transcribe')
    transcription_response = transcribe_file(file_uri, transcribe_client, job_name)

    # 3. Parse the JSON Response
    transcribed_data = correlate_speakers(transcription_response)

    # 5. Format into easy to follow text
    transcription_complete = output_transcription(transcribed_data)

    # 6. Give the user the option to remove files to reserve space
    if transcription_complete:
        reserve_space(job_name, file_name, s3_bucket_name)



if __name__ == '__main__':
    main()
