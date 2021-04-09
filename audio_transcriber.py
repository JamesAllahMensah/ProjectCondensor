import hashlib
import re
import urllib

import boto3
from botocore.exceptions import ClientError
import json
import logging
import glob, os
import pathlib
import googletrans
from google_trans_new import google_translator
import time
from fpdf import FPDF
from datetime import datetime
from pytz import timezone

# Author: James (Jimmy) Allah-Mensah
# Date: 2/25/21
# Version: Python 3.7

# Loads configuration setting given a key
'''
WatchWords (Array): Words whose times are automatically recorded and outputted to the search index PDF
MaxNumberSuggestions (Integer): The maximum number of suggestions that are to be displayed if the entered word or phrase does not exist
NameIntroductionWordBound (Integer): When identify speakers, any implicit or explicit phrase identified after nth word is disregarded
LanguageOptions (Dictionary): All language options that AWS Transcribe can handle, includes the Language as well as the associated Countries
IncludedLanguages (Array): Current language(s) identified in the transcription. Must have a minimum of two values to be counted
DefaultLanguage (String): The default transcription language assuming IncludedLanguages has less than the minimum required values (2).
MediaFormats (Array): All possible media formats that AWS Transcribe can handle
MediaFormat (String): Current desired media format
IntroductionCategories (Dictionary): The methods (phrases) in which a person introduces themselves
ExplicitIntroductionList (Array): The methods (phrases) where the chance of the person's name appearing after is high
MaxSpeakerLabels (Integer): The maximum number of speakers that can be identified. Max is 10.
EditConfigOnStart (Boolean): Asks the user if they would like to view/edit configurations at the start of the program
'''


def getConfiguration(key):
    with open('transcription_config.json') as file:
        data = json.load(file)
    return data[key]


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


# Searches for a file matching the desired media format within the script directory
def retrieve_audio():
    print('Retrieving Audio File(s)...')
    output_file = ''
    media_format = getConfiguration('MediaFormat')
    audio_files = []
    file_path = pathlib.Path(__file__).parent.absolute()
    os.chdir(file_path)
    for file in glob.glob("*.{}".format(media_format)):
        audio_files.append(file)

    if len(audio_files) == 0:
        print('No .{0} files were found. Please ensure that they are located in {1}'.format(media_format, file_path))
        return None

    elif len(audio_files) == 1:
        return audio_files[0]
    else:
        correct_file = input(
            '{0} .{1} files were found. Please enter the name of the desired audio file: (Enter L to list all .{1} files):'.format(
                len(audio_files), media_format))
        if correct_file.lower()[0] == 'l':
            for idx, val in enumerate(audio_files):
                print('{}: {}'.format(idx + 1, val))

            selected_file = input(
                'Please enter the file index (ex: 1) or the file name of the desired file (ex: {}):'.format(
                    audio_files[0]))
            if selected_file.isnumeric():
                while int(selected_file) > len(audio_files) or int(selected_file) > 0:
                    selected_file = input(
                        'Please enter the file index (ex: 1) or the file name of the desired file (ex: {}):'.format(
                            audio_files[0]))
                return audio_files[int(selected_file) - 1]
            else:
                while selected_file.lower() not in map(lambda x: x.lower(),
                                                       audio_files) and selected_file.lower() not in map(
                    lambda x: x.lower().replace(".{}".format(media_format), ""), audio_files):
                    selected_file = input(
                        'Could not find that file. Please re-enter the file index (ex: 1) or the file name of the desired file (ex: {}):'.format(
                            audio_files[0]))

                output_file = selected_file
        else:
            while correct_file.lower() not in map(lambda x: x.lower(), audio_files) and correct_file.lower() not in map(
                    lambda x: x.lower().replace(".{}".format(media_format), ""), audio_files):
                correct_file = input(
                    'Could not find that file. Please re-enter the file index (ex: 1) or the file name of the desired file (ex: {}):'.format(
                        audio_files[0]))

            output_file = correct_file

        if output_file not in audio_files:
            for audio_file in audio_files:
                if '.{}'.format(media_format) not in output_file:
                    if (output_file.lower() + '.{}'.format(media_format)) == audio_file.lower():
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
        print('Uploading file to S3 Bucket...')
        for bucket_file in s3_client.list_objects(Bucket=bucket)['Contents']:
            if file_name == bucket_file['Key'] or calculate_s3_etag(file_name) == bucket_file['ETag']:
                error_msg = input(
                    'File: {} already exists\nWould you like to overwrite this file (Y/N):'.format(file_name))
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
        error_msg = input(
            'Job Name: {} already exists. \nDo you want to override the existed job (Y/N):'.format(job_name))
        if error_msg.lower()[0] == 'y':
            job_name = input('Please enter a transcription job name:')
            while not is_job_name_unique(job_name):
                job_name = input(
                    'Job Name: {} already exists. Please enter a new transcription job name:'.format(job_name))
        else:
            return None

    language_options = getConfiguration("IncludedLanguages")
    if len(language_options) < 2:
        transcribe_client.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={'MediaFileUri': file_uri},
            MediaFormat=getConfiguration('MediaFormat'),
            LanguageCode=getConfiguration("DefaultLanguage"),
            Settings={
                'ShowSpeakerLabels': True,
                'MaxSpeakerLabels': getConfiguration('MaxSpeakerLabels')
            }
        )
    else:
        transcribe_client.start_transcription_job(
            TranscriptionJobName=job_name,
            Media={'MediaFileUri': file_uri},
            MediaFormat=getConfiguration('MediaFormat'),
            LanguageOptions=getConfiguration("IncludedLanguages"),
            Settings={
                'ShowSpeakerLabels': True,
                'MaxSpeakerLabels': getConfiguration('MaxSpeakerLabels')
            },
            IdentifyLanguage=True
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
            start_time = segment['start_time']
            end_time = segment['end_time']
            timestamp = str(time.strftime('%H:%M:%S', time.gmtime(round(float(start_time))))) + ' - ' \
                        + str(time.strftime('%H:%M:%S', time.gmtime(round(float(end_time)))))
            speaker = segment['speaker_label'].replace("spk_", "Speaker ")
            speaker = speaker.split(" ")[0] + " " + str(int(speaker[len(speaker) - 1]) + 1) + ":"
            segment_text = word_list[counter:counter + num_words]

            script = ''
            for x in segment_text:
                script += x + ' '
            full_transcription.append((speaker, script.rstrip(), timestamp))
            counter = counter + num_words

        for i in full_transcription:
            print(i[0].replace(":", " [") + i[2] + "]:")
            print(i[1] + "\n")
        return full_transcription


# Gives user an option to translate the text (supports over 40 languages)
def translate_script(transcription_response, transcribed_data):
    if transcribed_data is not None:
        response = urllib.request.urlopen(transcription_response)
        data = json.loads(response.read())
        language_code = data['results']['language_code']

        language_options = getConfiguration('LanguageOptions')
        for dialects in list(language_options.values()):
            for dialect in list(dialects.values()):
                if dialect == language_code:
                    detected_language = list(language_options.keys())[
                        list(language_options.values()).index(dialects)]
                    detected_dialect = list(dialects.keys())[list(dialects.values()).index(dialect)]
                    break

        print('The detected Language is: {}'.format(detected_language))
        translate_text = input(('Would you like to translate the transcribed audio?'))
        if translate_text[0].lower() == 'y':
            destination_language = input(
                'Please enter the destination lanuage or type in \'options\' for language options:').lower()
            while (destination_language not in list(
                    googletrans.LANGUAGES.values()) and destination_language not in list(
                googletrans.LANGUAGES.keys()) or (str(detected_language).lower() == destination_language.lower())):
                if 'option' in destination_language:
                    print('Language: Language Abbreviation')
                    for google_trans_option in googletrans.LANGUAGES:
                        print('{}: {}'.format(googletrans.LANGUAGES[google_trans_option], google_trans_option))
                if destination_language.lower() == str(detected_language).lower():
                    print('Destination language cannot be the same as the source language.')
                destination_language = input(
                    'Please enter the destination lanuage or type in \'options\' for language options:')

            if destination_language.lower() in list(googletrans.LANGUAGES.values()):
                destination_language = list(googletrans.LANGUAGES.keys())[
                    list(googletrans.LANGUAGES.values()).index(destination_language)]
            source_language = list(googletrans.LANGUAGES.keys())[
                list(googletrans.LANGUAGES.values()).index(str(detected_language).lower())]
            print('Initiating translation...')
            translated_transcribed_data = initiate_language_translation(transcribed_data, source_language, destination_language)
            return translated_transcribed_data
        else:
            return transcribed_data
    return None

# Translates the text from the detected source language to the provided destination language
def initiate_language_translation(transcribed_data, source_language, destination_language):
    print('Translating text...')
    translator = google_translator()
    translated_transcribed_data = []

    for index, value in enumerate(transcribed_data):
        transcription_entry = transcribed_data[index]
        translated_text = translator.translate(transcription_entry[1], lang_src=source_language,
                                               lang_tgt=destination_language)
        translation_package = (transcription_entry[0], translated_text, transcription_entry[2])
        translated_transcribed_data.append(translation_package)

    print('Translation from {} to {} complete!'.format(googletrans.LANGUAGES[source_language].capitalize(),
                                                       googletrans.LANGUAGES[destination_language].capitalize()))
    return translated_transcribed_data


# Attempts to identify the speaker's names
def identify_speakers(full_transcription):
    print('Attempting to identifying speakers names...')
    # Six most common ways in which people introduce themselves
    intro_category = getConfiguration("IntroductionCategories")

    # Introduction methods where the chance of the speakers name appearing directly after the phrase is high
    # Ex: 'My name is [James]', 'I go by [James]'
    explicit_list = getConfiguration("ExplicitIntroductionList")

    # Any word said after the nth word no longer counts as a name
    # Speaker is expected to introduce themselves early on
    max_word_index = getConfiguration("NameIntroductionWordBound")

    full_speaker_script = {}
    for script in full_transcription:
        speaker = script[0].replace(":", "")
        transcript = script[1]
        if not speaker in full_speaker_script:
            full_speaker_script[speaker] = re.sub(r'[^\w\s]', '', transcript)
        else:
            full_speaker_script[speaker] += re.sub(r'[^\w\s]', '', transcript)

    identified_speakers = {}
    for speaker_script in full_speaker_script:
        regex_script = full_speaker_script[speaker_script].lower()
        for category in intro_category:
            search_phrase = re.sub(r'[^\w\s]', '', intro_category[category]).lower()
            num_matches = len(re.findall('{}'.format(search_phrase), regex_script))
            if category in explicit_list:
                if num_matches > 0:
                    match = re.search('(?<={} )(.*)'.format(search_phrase), regex_script)
                    if match is not None:
                        name = match.groups()[0].split(' ')[0].capitalize()
                        identified_speakers[speaker_script] = name
                        break
            else:
                if num_matches > 0:
                    name_list = []
                    for i in range(num_matches):
                        match = re.search('(?<={} )(.*)'.format(search_phrase), regex_script)
                        if match is None:
                            continue
                        word_index = regex_script.split(' ').index(match.groups()[0].split(' ')[0])
                        name = match.groups()[0].split(' ')[0].capitalize()
                        if name.isalpha() and word_index <= max_word_index:
                            identified_speakers[speaker_script] = name
                            break
                        else:
                            regex_script = regex_script.replace('{}'.format(search_phrase), '', 1)

        if not speaker_script in identified_speakers:
            identified_speakers[speaker_script] = speaker_script

    return identified_speakers


# Helper method used to compare the different letters given two n-sized strings
def diff_letters(a, b):
    return sum(a[i] != b[i] for i in range(len(a)))


# 7. Identify when the user said a specific word or phrase (If none found, suggestions are made)
def get_time_from_word(transcription_response, speakers, is_watch_word, watch_word):
    formatted_speakers = {}
    for speaker in speakers:
        format_speaker = speaker.replace("Speaker", "spk").replace(" ", "_")
        formatted_speakers[format_speaker] = speakers[speaker]

    speakers = formatted_speakers
    detection = input('Please enter a word or phrase: ').lower()
    if is_watch_word:
        detection = watch_word.lower()

    speaker_dict = {}
    detected_times = []
    num_suggestions = getConfiguration("MaxNumberSuggestions")
    found = False

    if ' ' in detection:
        while not found:
            word_list = detection.split(' ')
            initial_word = word_list[0]
            ignored_index = []
            suggestion_index = []
            if transcription_response is not None:
                response = urllib.request.urlopen(transcription_response)
                data = json.loads(response.read())
                segments = data['results']['items']
                suggestions = {}
                segment_index = 0
                while segment_index < len(segments):
                    type = segments[segment_index]['type']
                    if type == 'punctuation':
                        segment_index += 1
                        continue
                    word = segments[segment_index]['alternatives'][0]['content'].lower()
                    raw_start_time = segments[segment_index]['start_time']
                    start_time = str(
                        time.strftime('%H:%M:%S', time.gmtime(round(float(segments[segment_index]['start_time'])))))
                    if word == initial_word and segment_index not in ignored_index:
                        if segment_index + len(word_list) <= len(segments):
                            match_start = 1
                            while match_start < len(word_list):
                                compare_word = word_list[match_start]
                                if compare_word != segments[segment_index + match_start]['alternatives'][0][
                                    'content'].lower():
                                    ignored_index.append(segment_index)
                                    segment_index = 0
                                    break
                                match_start += 1
                            if match_start == len(word_list):
                                detected_times.append((detection, start_time, raw_start_time))
                                ignored_index.append(segment_index)
                                segment_index = 0
                    if len(word) == len(initial_word):
                        char_compare = diff_letters(word, initial_word)
                        if segment_index + len(word_list) <= len(
                                segments) and segment_index not in suggestion_index:
                            adequate_compare = False
                            for comp_index in range(num_suggestions + 1):
                                if char_compare == comp_index:
                                    adequate_compare = True
                            if adequate_compare:
                                match_start = 1
                                total_compare_cnt = char_compare
                                full_suggestion = word
                                while match_start < len(word_list):
                                    compare_word = word_list[match_start]
                                    if len(compare_word) == len(segments[segment_index + match_start][
                                                                    'alternatives'][0][
                                                                    'content'].lower()):
                                        compare_cnt = diff_letters(compare_word,
                                                                   segments[segment_index + match_start][
                                                                       'alternatives'][0][
                                                                       'content'].lower())

                                        total_compare_cnt += compare_cnt
                                        if compare_word != segments[segment_index + match_start]['alternatives'][0][
                                            'content'].lower() and compare_cnt > num_suggestions:
                                            suggestion_index.append(segment_index)  # suggestion_index.append
                                            segment_index = 0
                                            break
                                        full_suggestion = full_suggestion + " " + \
                                                          segments[segment_index + match_start]['alternatives'][0][
                                                              'content'].lower()
                                    else:
                                        break
                                    match_start += 1
                                if match_start == len(word_list):
                                    suggestions[full_suggestion] = total_compare_cnt

                    segment_index += 1

                if len(detected_times) > 0:
                    print('The phrase: \'{}\' was mentioned {} times during the following time(s):'.format(detection,
                                                                                                           len(

                                                                                                               detected_times)))
                    speaker_segment = data['results']['speaker_labels']['segments']
                    for spk_segment in speaker_segment:
                        spk_items = spk_segment['items']
                        for spk_item in spk_items:
                            spk_start_time = spk_item['start_time']
                            spk_label = spk_item['speaker_label'].split("_")[0] + "_" + str(
                                int(spk_item['speaker_label'].split("_")[1]) + 1)
                            for det_time in detected_times:
                                if det_time[2] == spk_start_time:
                                    speaker_dict[
                                        str(time.strftime('%H:%M:%S', time.gmtime(round(float(spk_start_time)))))] = \
                                        speakers[spk_label]

                    print('The phrase: \'{}\' was mentioned {} times during the following time(s):'.format(detection,
                                                                                                           len(

                                                                                                               detected_times)))

                    return_dict = {
                        detection: {

                        }
                    }
                    for index, value in enumerate(detected_times):
                        print('{}: '.format(speaker_dict[value[1]]) + value[1])
                        if speaker_dict[value[1]] not in return_dict[detection]:
                            return_dict[detection][speaker_dict[value[1]]] = [value[1]]
                        else:
                            return_dict[detection][speaker_dict[value[1]]].append(value[1])

                    found = True
                    return return_dict

                else:
                    if is_watch_word:
                        return None

                    exact_match = 0
                    for suggest in suggestions:
                        for indiv_word in word_list:
                            if suggest == indiv_word:
                                exact_match += 1
                                exact_match = exact_match * -1
                                suggestions[suggest] = exact_match

                    suggestions = list(dict(sorted(suggestions.items(), key=lambda item: item[1])))

                    if len(suggestions) > 0:
                        if len(suggestions) > num_suggestions:
                            del suggestions[num_suggestions: len(suggestions)]
                        print('Could not identify the phrase within the transcribe text.')
                        for index, val in enumerate(suggestions):
                            print(str(index + 1) + ": " + val)

                        try_again = input(
                            'No matches found. Did you mean any of the above? Enter an associented number, another '
                            'phrase or type in \'Q\' to quit').lower()
                        if try_again == 'q':
                            return
                        elif try_again.isnumeric():
                            detection = suggestions[int(try_again) - 1]
                        else:
                            detection = try_again
                    else:
                        print('Could not identify the phrase within the transcribe text.')
                        detection = input('Please enter a new phrase or enter \'Q\' to quit').lower()
                        if detection == 'q':
                            return
    else:
        while not found:
            if transcription_response is not None:
                response = urllib.request.urlopen(transcription_response)
                data = json.loads(response.read())
                segments = data['results']['items']
                suggestion_list = {}
                for segment in segments:
                    word = segment['alternatives'][0]['content'].lower()
                    if word == detection:  # If we did find the word, retrieve the time
                        start_time = str(time.strftime('%H:%M:%S', time.gmtime(round(float(segment['start_time'])))))
                        raw_start_time = segment['start_time']
                        detected_times.append((detection, start_time, raw_start_time))
                        found = True

                    else:  # If we did not find the word, find a similar word and add it as a suggestion
                        if len(word) == len(detection):
                            char_compare = diff_letters(word, detection)
                            if char_compare == 1 or char_compare == 2 or char_compare == 3:
                                if word not in suggestion_list:
                                    suggestion_list[word.capitalize()] = char_compare

                if not found:
                    if is_watch_word:
                        return None
                    suggestion_list = list(dict(sorted(suggestion_list.items(), key=lambda item: item[1])))

                    if len(suggestion_list) > 0:
                        if len(suggestion_list) > num_suggestions:
                            del suggestion_list[num_suggestions: len(suggestion_list)]
                        print('Could not identify the word within the transcribe text.')
                        for index, val in enumerate(suggestion_list):
                            print(str(index + 1) + ": " + val)

                        searched_index = input('Did you mean any of the above? (Enter the associated '
                                               'number, type in Q to quit, or type in R to enter a new value):')
                        searched_index = re.sub(r'[^\w\s]', '', searched_index)
                        if searched_index.isalpha():
                            if searched_index.lower() == 'q':
                                return
                            else:
                                detection = input('Please enter a word: ').lower()
                                continue
                        else:
                            searched_index = int(searched_index)

                        while searched_index > len(suggestion_list):
                            print('Invalid word association. Please try again.')
                            for index, val in enumerate(suggestion_list):
                                print(str(index + 1) + ": " + val)

                            searched_index = input('Did you mean any of the above? (Enter the associated '
                                                   'number, type in Q to quit, or type in R to enter a new value):')
                            searched_index = re.sub(r'[^\w\s]', '', searched_index)
                            if searched_index.isalpha():
                                return
                            else:
                                searched_index = int(searched_index)

                        detection = suggestion_list[searched_index - 1].lower()
                    else:
                        print('Could not identify the word within the transcribe text, no suggestions available.')
                        detection = input('Please enter another word or enter Q to quit: ').lower()

                        if detection == 'q':
                            return
                else:
                    print('The word: \'{}\' was mentioned {} times during the following time(s):'.format(detection,
                                                                                                         len(

                                                                                                             detected_times)))
                    speaker_segment = data['results']['speaker_labels']['segments']
                    for spk_segment in speaker_segment:
                        spk_items = spk_segment['items']
                        for spk_item in spk_items:
                            spk_start_time = spk_item['start_time']
                            spk_label = spk_item['speaker_label'].split("_")[0] + "_" + str(
                                int(spk_item['speaker_label'].split("_")[1]) + 1)
                            for det_time in detected_times:
                                if det_time[2] == spk_start_time:
                                    speaker_dict[
                                        str(time.strftime('%H:%M:%S', time.gmtime(round(float(spk_start_time)))))] = \
                                        speakers[spk_label]

                    return_dict = {
                        detection: {

                        }
                    }
                    for index, value in enumerate(detected_times):
                        print('{}: '.format(speaker_dict[value[1]]) + value[1])
                        if speaker_dict[value[1]] not in return_dict[detection]:
                            return_dict[detection][speaker_dict[value[1]]] = [value[1]]
                        else:
                            return_dict[detection][speaker_dict[value[1]]].append(value[1])

                    return return_dict


# Writes the formatted transcription to a PDF file
def output_transcription(transcribed_data, job_name, speaker_dict):
    if transcribed_data is None:
        return False

    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=20)
    pdf.cell(200, 10, txt=job_name.replace("_", " ").title(), ln=1, align='C')

    tz = timezone('EST')
    date = str(datetime.now(tz).strftime('%m/%d/%y %I:%M %p'))
    pdf.set_font("Arial", size=15)
    pdf.cell(200, 10, txt=date, ln=2, align='C')

    print('Printing the output to a PDF file...')
    pdf.set_font("Helvetica", size=12)
    line_cnt = 5
    max_length = 90

    for i in transcribed_data:
        speaker = i[0]
        speaker_num = speaker_dict[speaker.replace(":", "")]
        pdf.set_font("Helvetica", 'B', size=12)
        pdf.cell(200, 10, txt=speaker_num + " [" + i[2] + "]:", ln=line_cnt, align='L')
        pdf.set_font("Helvetica", size=12)
        line_cnt += 1
        output_text_line_1 = i[1]
        if len(output_text_line_1) > max_length:
            split_index = max_length
            while len(output_text_line_1) > max_length:
                if output_text_line_1[max_length].isalnum():
                    while output_text_line_1[split_index].isalnum():
                        split_index -= 1
                split_text = output_text_line_1[0: split_index]
                output_text_line_1 = output_text_line_1[split_index:len(output_text_line_1)]
                pdf.cell(200, 10, txt=split_text.lstrip(), ln=line_cnt, align='L')
                line_cnt += 1
            pdf.cell(200, 10, txt=output_text_line_1.lstrip(), ln=line_cnt, align='L')
            line_cnt += 2
        else:
            pdf.cell(200, 10, txt=output_text_line_1, ln=line_cnt, align='L')
            line_cnt += 2

        pdf.cell(200, 10, txt='', ln=line_cnt, align='L')

    pdf.set_font("Helvetica", size=10)
    pdf.cell(200, 10, txt='Transcription made possible using AWS Transcribe.', ln=line_cnt + 1, align='L')
    pdf.output('{}.pdf'.format(job_name.replace("_", " ")).title())
    return True


# Identifies when the user said a specific word or phrase, output to a pdf file.
def recordTimes(speakers, job_name, transcription_response):
    search_text = input('Transcription complete! Would you like to search the transcribed text for specific words or '
                        'phrases (Y/N):')

    recorded_times = {}
    job_name = job_name.replace('_', ' ').capitalize()
    if search_text.lower()[0] == 'y':
        continue_search = True
        while continue_search:
            detected_times = get_time_from_word(transcription_response, speakers, False, None)
            if detected_times is not None:
                recorded_times[list(detected_times.keys())[0]] = detected_times[list(detected_times.keys())[0]]
            another_search = input('Would you like to search for another word or phrase?')
            if another_search.lower()[0] != 'y':
                continue_search = False
            # Iterate through watch words, pass in true as blocklist , if not none add to recorded_times
        print('Searching for Watch Words...')
        watch_words = getConfiguration("WatchWords")
        for watch_word in watch_words:
            watch_word_detection = get_time_from_word(transcription_response, speakers, True, watch_word)
            if watch_word_detection is not None:
                recorded_times[list(watch_word_detection.keys())[0]] = watch_word_detection[
                    list(watch_word_detection.keys())[0]]
        record = input('Would you like to record these times (Y/N):')
        if record.lower()[0] == 'y':
            time_segments = list(recorded_times.values())
            speaker_list = []
            for time in time_segments:
                speakers = time
                for speaker in list(speakers.keys()):
                    if speaker not in speaker_list:
                        speaker_list.append(speaker)
            word_cnt = 0
            word_frequency = {}
            for rec_time in recorded_times:
                word_cnt = 0
                for rec_speakers in recorded_times[rec_time]:
                    for rec_time_seg in recorded_times[rec_time][rec_speakers]:
                        word_cnt += 1

                word_frequency[rec_time] = word_cnt
            pdf = FPDF()
            pdf.add_page()
            pdf.set_font("Arial", size=20)
            pdf.cell(200, 10, txt=job_name.replace("_", " ").title() + " Search Index", ln=1, align='C')
            line_cnt = 5
            for word_or_phrase in recorded_times:
                time_frequency = word_frequency[word_or_phrase]
                pdf.set_font("Arial", 'B', size=16)
                pdf.cell(200, 10, txt='', ln=line_cnt, align='L')
                line_cnt += 1
                pdf.cell(200, 10, txt="\'{}\' ".format(word_or_phrase.capitalize()), ln=line_cnt, align='L')
                line_cnt += 1
                pdf.set_font("Arial", '', size=14)
                if time_frequency == 1:
                    pdf.cell(200, 10, txt="mentioned {} time \n".format(time_frequency), ln=line_cnt, align='L')
                else:
                    pdf.cell(200, 10, txt="mentioned {} times \n".format(time_frequency), ln=line_cnt, align='L')

                for speaker in speaker_list:
                    if speaker in list(recorded_times[word_or_phrase].keys()):
                        pdf.cell(200, 10, txt='', ln=line_cnt, align='L')
                        line_cnt += 1
                        pdf.cell(200, 10, txt='{} \n'.format(speaker), ln=line_cnt, align='L')
                        line_cnt += 1
                        time_stamps = recorded_times[word_or_phrase][speaker]
                        for time_stamp in time_stamps:
                            pdf.cell(200, 10, txt='{} \n'.format(time_stamp), ln=line_cnt, align='L')
                            line_cnt += 1
                    line_cnt += 2
            job_name += ' Search Index'
            pdf.output('{}.pdf'.format(job_name.replace("_", " ")).title())
            return True
    return False


# Deletes the audio file from the S3 bucket & the transcription job
def reserve_space(job_name, object_key, bucket):
    reserve = input('Would you like to delete the transcription job and audio file to reserve space (Y/N):')
    if reserve.lower()[0] == 'y':
        try:
            s3_client = boto3.client('s3')
            s3_transcribe_client = boto3.client('transcribe')
            s3_client.delete_object(Bucket=bucket, Key=object_key)
            s3_transcribe_client.delete_transcription_job(TranscriptionJobName=job_name)
            print('Job {} & File {} have successfully been deleted.'.format(job_name, object_key))
        except ClientError as e:
            logging.error(e)


def transcribe_audio():
    # Loads AWS S3 bucket information, with preference option
    s3_bucket_name = get_s3_bucket(None)

    # Searches for a file matching the desired media format within the script directory
    file_name = retrieve_audio()

    # 1. Upload file to AWS S3 Bucket
    file_uri = upload_file(file_name, s3_bucket_name)

    # 2. Create the Transcription Job
    job_name = input('Please enter a transcription job name:').replace(" ", "_")
    transcribe_client = boto3.client('transcribe')
    transcription_response = transcribe_file(file_uri, transcribe_client, job_name)

    # 3. Parse the JSON Response
    transcribed_data = correlate_speakers(transcription_response)

    # 4. Gives user an option to translate the text (supports over 40 languages)
    transcribed_data = translate_script(transcription_response, transcribed_data)

    # 5. Attempt to identify speaker names
    speaker_names = identify_speakers(transcribed_data)

    # 6. Writes transcribed text to a PDF file
    transcription_complete = output_transcription(transcribed_data, job_name, speaker_names)

    # 7. Identify when the user said a specific word or phrase, output to a pdf file.
    time_retrievals = recordTimes(speaker_names, job_name, transcription_response)

    # 8. Give the user the option to remove files to reserve space
    if transcription_complete:
        reserve_space(job_name, file_name, s3_bucket_name)


def main():
    transcribe_audio()

    # print('Transcribing Powerpoint Slides')
    # condensor_pdf()


if __name__ == '__main__':
    main()
