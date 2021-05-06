Project Condenser - Audio Transcription

Author:
James (Jimmy) Allah-Mensah is a Computer Science & Cyber Security student at Christopher Newport University who will be graduating on May 15th, 2021. He’s worked with General Dynamics Information Technology for about a year as a Software Development Intern. James will be starting his career in July as a software engineer at JP Morgan Chase & Co. in Columbus, Ohio following graduation.

About:
Project Condenser is a pipeline allowing video multimedia formatted files to be exported into easily digestible formats. The two parts to this project were the Video Summarization and Audio Transcription components.

This repository contains the code used for the Audio Transcription component. The two files in this repository are audio_transcriber.py and transcription_config.json. Transcription_config.json is a json file with several settings that the audio transcription service relies on. The settings and their descriptions are in the configuration section. The audio_transcriber.py is a python file that contains the code that actually transcribes the audio file. It has several fascinating features that are explained in the ‘High Level Process’ section.

Configurations:
WatchWords (Array): Words whose times are automatically recorded and outputted to the search index PDF 
MaxNumberSuggestions (Integer): The maximum number of suggestions that are to be displayed if the entered word or phrase does not exist 
NameIntroductionWordBound (Integer): When identify speakers, any implicit or explicit phrase identified after nth word is disregarded 
LanguageOptions (Dictionary): All language options that AWS Transcribe can handle, includes the Language as well as the associated Countries 
IncludedLanguages (Array): Current language(s) identified in the transcription. Must have a minimum of two values to be counted 
DefaultLanguage (String): The default transcription language assuming IncludedLanguages has less than the minimum required values (2). 
MediaFormats (Array): All possible media formats that AWS Transcribe can handle MediaFormat (String): Current desired media format 
IntroductionCategories (Dictionary): The methods (phrases) in which a person introduces themselves 
ExplicitIntroductionList (Array): The methods (phrases) where the chance of the person's name appearing after is high 
MaxSpeakerLabels (Integer): The maximum number of speakers that can be identified. Max is 10. 
EditConfigOnStart (Boolean): Asks the user if they would like to view/edit configurations at the start of the program

Steps with Details:
There are seven steps, two being optional, that are used in the audio transcription
1. We read preferences from the configuration file. These preferences include several watch words that we look out for such as, Artificial Intelligence, Cloud and Cyber, max number of speakers identified, and the different possible media formats

2. An algorithm identifies all audio files within the scripts directory
If there’s only one audio file matching the desired audio format in the directory, it pulls that one, if multiple it lists them out and asks the user to enter either the name of the file or its number in the list
Once it has the audio file, it compares the etag, the MD5 hash, of it with that of the other files in the S3 bucket, and if unique we upload the file to the S3 bucket

3. Once the file is uploaded, we ask a user for a transcription job name. If the name is unique, we take the URI of the audio file within the S3 bucket and start the transcription
The length of the transcription depends on the size of the audio file, but the transcription job is incredibly fast. It transcribes a 5 minute mp4 file in about 45 seconds.
Once the transcription job is complete, a JSON URL response with the transcription data is returned

4. We open the JSON file and parse it into an easily readable format that links the transcribed text to the speaker
After the speakers are correlated, we give the user the option to translate the text into one of 44 languages supported by the google translate api
Here, the source language and dialect are detected, and if a user enters one of the 44 language codes when asked for a destination language, the translation happens instantly.

5. After the translation is complete, assuming the user selects that option, an additional algorithm parses through the transcribed text and attempts to identify the names of the individual speakers.
What happens here is, the algorithm looks for the most common phrases where an individual introduces themselves such as “My name is,” grabs the name and replaces it with the generic “Speaker” and number.
If there aren’t any names identified, it keeps the Speaker and number label

6. Once the speakers have attempted to be identified, the interactive word phrase search index feature, my personal favorite, starts
With this feature, the console asks the user to enter a word or phrase that they may have heard from the audio. If identified in the transcription, the times as well as the speaker that said the word or phrase is returned, and printed to a separate PDF file.
The cool thing about this feature is that it offers word and phrase suggestions in case the word was not found or spelled incorrectly
The suggestions are the same length as the entered word, and the number of suggestions can be managed by editing the configuration file
This feature also looks for the watch words in the configuration file too, and if identified writes them to the PDF with the entered words or phrases

Once the user is done searching for words or phrases, the transcription output is nicely formatted into a PDF File with the transcription job name at the top, as well as the date and time of the transcription

7. Last but not least, the user is given an option to remove the transcription job and audio file from the S3 bucket

Technologies Used:
The service that we used to transcribe the audio files is AWS Transcribe, an automatic speech recognition service that makes it easy for developers to add speech to text capability in their applications. It uses a deep learning process called automatic speech recognition, or ASR, to convert text quickly and accurately. The other S3 service that we use is the Simple Storage Service, or S3. Amazon S3 is an object storage service that offers industry-leading scalability, data availability, security, and performance. The programming language used throughout the project is python. Python is an interpreted and object oriented high level programming language with dynamic semantics. Since the syntax is very easy to understand it also makes the code easy to maintain. It also supports a vast number of libraries used for almost anything. The three main libraries that are used in this project are the Boto3 Client, an AWS Software Development Kit, Google Trans API, a library that uses google cloud to translate text from a source to destination language, and PyFPDF, a PDF generator

Configuring AWS CLI:
In order to use the Boto 3 Client, one must first configure the AWS Command Line Interface which is used to interact with AWS. These include security credentials, default output format and the default AWS Region. Either follow the link or steps below:

Link: https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-quickstart.html

Steps (If Not Following Link):

1. Sign in to the AWS Management Console and open the IAM console at https://console.aws.amazon.com/iam/.

2. In the navigation pane, choose Users

3. Choose the name of the user whose access keys you want to create, and then choose the Security credentials tab.

4. In the Access keys section, choose Create access key

5. To view the new access key pair, choose Show. You will not have access to the secret access key again after this dialog box closes. Your credentials will look something like this: 
	Access key ID: AKIAIOSFODNN7EXAMPLE 
	Secret access key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY

6. To download the key pair, choose Download .csv file. Store the keys in a secure location. You will not have access to the secret access key again after this dialog box closes.

7. Keep the keys confidential in order to protect your AWS account and never email them. Do not share them outside your organization, even if an inquiry appears to come from AWS or Amazon.com. No one who legitimately represents Amazon will ever ask you for your secret key.

8. After you download the .csv file, choose Close. When you create an access key, the key pair is active by default, and you can use the pair right away.

9. In the command line, run the following command and enter in the following information:

	aws configure
	AWS Access Key ID [None]: {Enter Key ID}
	AWS Secret Access Key [None]: {Enter Secret Access Key}
	Default region name [None]: {Enter region name: ex: us-west-2}
	Default output format [None]: {Enter output format: ex: json}

Next Steps:

Create a GUI for the program. (Ex: Drag and Drop Audio Files into a window for detection, Click a button to start the transcription job, etc.)

Offer more output options (Ex: .docx, .doc, .rtf)


