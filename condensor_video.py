import numpy as np
import random
from PIL import Image as im
from fpdf import *
import os
import time

env = os.environ
target = "IMAGEIO_FFMPEG_EXE"
path = "/Users/stefanjp/Downloads/ffmpeg"
env[target] = path
from moviepy.editor import *


def get_dimensions(video_clip):
    return video_clip.size


def uniform_sample(dimension):
    return [int(random.uniform(0, dimension[1])), int(random.uniform(0, dimension[0]))]


def create_samples(amount, dimension):
    pixels = []
    for x in range(amount):
        pixels.append(uniform_sample(dimension))
    return pixels


def get_pixel_values_single(frame, pixel):
    return frame[pixel[0]][pixel[1]]


def get_pixel_values_all(frame, pixels):
    values = []
    for x in range(len(pixels)):
        value = get_pixel_values_single(frame, pixels[x])
        values.append(value)
    return values


def average_RGB_value(RGBvals):
    length = len(RGBvals)
    r = 0
    g = 0
    b = 0

    for vals in RGBvals:
        r += vals[0]
        g += vals[1]
        b += vals[2]
    return [r / length, g / length, b / length]


def color_difference(a, b):
    return (((b[0] - a[0]) ** 2) + ((b[1] - a[1]) ** 2) + ((b[2] - a[2]) ** 2) ** .5)


def initialize_values(video_clip, samples):
    return update_values(video_clip, 0, samples)


def update_values(video_clip, frameNum, samples):
    return average_RGB_value(get_pixel_values_all(video_clip.get_frame(frameNum), samples))


def frame_iteration(filename, timeThreshold, changeThreshold, amountOfSamples):
    clip = VideoFileClip(filename)
    frames = int((clip.duration))
    dimensions = get_dimensions(clip)
    samples = create_samples(amountOfSamples, dimensions)
    reference_value = initialize_values(clip, samples)
    current_value = reference_value
    timestamps = []

    currentFrame = 0
    while currentFrame <= frames and currentFrame < 4100:

        current_value = update_values(clip, currentFrame, samples)

        if color_difference(current_value, reference_value) > changeThreshold:
            timestamps.append(currentFrame)
            reference_value = current_value
            print(currentFrame)
            currentFrame = currentFrame + (timeThreshold - 1)
        currentFrame += 1
    print(len(timestamps))
    clip.close()
    return timestamps


def write_to_PDF(timestamps, clip_filename):
    clip = VideoFileClip(clip_filename)
    pdf = FPDF(orientation='P')
    pdf.add_page()
    desktop = desktop = os.path.join(os.path.join(os.path.expanduser('~')), 'Desktop')
    newPath = "condensor"
    path = os.path.join(desktop, newPath)
    i = 0
    print(path)
    try:
        os.mkdir(path)
    except:
        1 + 1
    for times in timestamps:
        img = clip.get_frame(times)
        picture = im.fromarray(img)
        print(img.size)
        print(img.shape)
        newsize = (int(img.shape[0] / 2), int(img.shape[1] / 2))
        picture.thumbnail(newsize, im.ANTIALIAS)
        print(type(img))
        # picture = im.fromarray(img)
        print(type(picture))
        picture.save(path + "/tmp" + str(i) + ".png", "PNG")
        pdf.image(path + "/tmp" + str(i) + ".png")
        os.remove(path + "/tmp" + str(i) + ".png")
        if i + 1 < len(timestamps):
            pdf.add_page()
        i = i + 1
    pdf.output(path + "/condensor.pdf", "F")
    clip.close()


string = "/Users/stefanjp/12403/Spring Innovation Expo 2021-04-29-14-44-28.mp4"
times = frame_iteration(string, 10, 10, 20)
write_to_PDF(times, string)
