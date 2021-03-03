import http
import time
import urllib

import boto3
from botocore.exceptions import ClientError
import json
import requests
import logging
import uuid

# Author: James (Jimmy) Allah-Mensah
# Date: 2/25/21
# Version: Python 3.7


# Uploads the local file into the S3 bucket and returns the file URI
def upload_file(file_name, bucket, object_name=None):
    if object_name is None:
        object_name = file_name

    s3_client = boto3.client('s3')
    try:
        response = s3_client.upload_file(file_name, bucket, object_name)
        file_path = 's3://condensor/' + file_name
    except ClientError as e:
        logging.error(e)
        return None
    return file_path


# Checks if the job name already exists
def is_job_name_unique(job_name):
    s3_client = boto3.client('transcribe')
    transcription_jobs = s3_client.list_transcription_jobs()['TranscriptionJobSummaries']
    for job in transcription_jobs:
        if job['TranscriptionJobName'] == job_name and job['TranscriptionJobStatus'] == 'COMPLETED':
            return False

    return True



# Starts the transcription job and returns a json file when complete
def transcribe_file(job_name, file_uri, transcribe_client):

    if is_job_name_unique(job_name):
        error_msg = 'Job Name: {} already exists.'.format(job_name)
        print(error_msg)
        return

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
    f = open("Output.txt", "w")
    for i in transcribed_data:
        f.write(i[0] + "\n")
        f.write(i[1] + "\n")
        f.write("\n")
    f.close()


def main():
    s3_bucket_name = 'condensor'
    transcription_job_name = str(uuid.uuid4())

    # 1. Upload file to AWS S3 Bucket
    print('Uplading file to S3 Bucket...')
    file_uri = upload_file('Sample_Audio.mp4', s3_bucket_name)

    # 2. Create the Transcription Job
    print('Transcribing file...')
    transcribe_client = boto3.client('transcribe')
    transcription_response = transcribe_file(transcription_job_name, file_uri, transcribe_client)

    # 3. Parse the JSON Response
    print('Identifying the speakers and formatting text...')
    transcribed_data = correlate_speakers(transcription_response)

    # 5. Format into easy to follow text
    print('Printing the output to a text file...')
    output_transcription(transcribed_data)
    print('Transcription Complete!')



if __name__ == '__main__':
    main()
