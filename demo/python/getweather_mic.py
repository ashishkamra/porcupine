#
# Copyright 2018-2020 Picovoice Inc.
#
# You may not use this file except in compliance with the license. A copy of the license is located in the "LICENSE"
# file accompanying this source.
#
# Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
# an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
# specific language governing permissions and limitations under the License.
#

import argparse
import os
import struct
from datetime import datetime
from threading import Thread

import numpy as np
import pvporcupine
import pyaudio
import soundfile

import requests

from google.cloud import texttospeech

from pydub import AudioSegment
from pydub.playback import play

class PorcupineDemo(Thread):
    """
    Microphone Demo for Porcupine wake word engine. It creates an input audio stream from a microphone, monitors it, and
    upon detecting the specified wake word(s) prints the detection time and wake word on console. It optionally saves
    the recorded audio into a file for further debugging.
    """

    def __init__(
            self,
            library_path,
            model_path,
            keyword_paths,
            sensitivities,
            input_device_index=None,
            output_path=None):

        """
        Constructor.

        :param library_path: Absolute path to Porcupine's dynamic library.
        :param model_path: Absolute path to the file containing model parameters.
        :param keyword_paths: Absolute paths to keyword model files.
        :param sensitivities: Sensitivities for detecting keywords. Each value should be a number within [0, 1]. A
        higher sensitivity results in fewer misses at the cost of increasing the false alarm rate. If not set 0.5 will
        be used.
        :param input_device_index: Optional argument. If provided, audio is recorded from this input device. Otherwise,
        the default audio input device is used.
        :param output_path: If provided recorded audio will be stored in this location at the end of the run.
        """

        super(PorcupineDemo, self).__init__()

        self._library_path = library_path
        self._model_path = model_path
        self._keyword_paths = keyword_paths
        self._sensitivities = sensitivities
        self._input_device_index = input_device_index

        self._output_path = output_path
        if self._output_path is not None:
            self._recorded_frames = []

    def run(self):
        """
         Creates an input audio stream, instantiates an instance of Porcupine object, and monitors the audio stream for
         occurrences of the wake word(s). It prints the time of detection for each occurrence and the wake word.
         """

        keywords = list()
        for x in self._keyword_paths:
            keywords.append(os.path.basename(x).replace('.ppn', '').split('_')[0])

        porcupine = None
        pa = None
        audio_stream = None
        try:
            porcupine = pvporcupine.create(
                library_path=self._library_path,
                model_path=self._model_path,
                keyword_paths=self._keyword_paths,
                sensitivities=self._sensitivities)

            pa = pyaudio.PyAudio()

            audio_stream = pa.open(
                rate=porcupine.sample_rate,
                channels=1,
                format=pyaudio.paInt16,
                input=True,
                frames_per_buffer=porcupine.frame_length,
                input_device_index=self._input_device_index)

            print('Listening {')
            for keyword, sensitivity in zip(keywords, self._sensitivities):
                print('  %s (%.2f)' % (keyword, sensitivity))
            print('}')

            while True:
                pcm = audio_stream.read(porcupine.frame_length)
                pcm = struct.unpack_from("h" * porcupine.frame_length, pcm)

                if self._output_path is not None:
                    self._recorded_frames.append(pcm)

                result = porcupine.process(pcm)
                if result >= 0:
                    print('[%s] Detected %s' % (str(datetime.now()), keywords[result]))
                    
                    # weather 
                    weather = get_weather()
                    spoken_weather = extract_spoken_weather(weather)
                    print(spoken_weather)

                    text_to_speech(spoken_weather)

        except KeyboardInterrupt:
            print('Stopping ...')
        finally:
            if porcupine is not None:
                porcupine.delete()

            if audio_stream is not None:
                audio_stream.close()

            if pa is not None:
                pa.terminate()

            if self._output_path is not None and len(self._recorded_frames) > 0:
                recorded_audio = np.concatenate(self._recorded_frames, axis=0).astype(np.int16)
                soundfile.write(self._output_path, recorded_audio, samplerate=porcupine.sample_rate, subtype='PCM_16')

    @classmethod
    def show_audio_devices(cls):
        fields = ('index', 'name', 'defaultSampleRate', 'maxInputChannels')

        pa = pyaudio.PyAudio()

        for i in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(i)
            print(', '.join("'%s': '%s'" % (k, str(info[k])) for k in fields))

        pa.terminate()

def get_weather():

    # latitude and longitude to be parameterized, right now it is for Arlington, MA
    url = "https://dark-sky.p.rapidapi.com/42.42,-71.16"

    querystring = {"lang":"en","units":"auto"}

    headers = {
        'x-rapidapi-key': str(os.environ['DARK_SKY_API_KEY']),
        'x-rapidapi-host': "dark-sky.p.rapidapi.com"
    }

    response = requests.request("GET", url, headers=headers, params=querystring)

    return response.json()

def extract_spoken_weather(weather_response):

    #extract key pieces of weather information. To be parametrized later.i
    hourly_weather_0_time = datetime.fromtimestamp(weather_response["hourly"]["data"][0]["time"]).strftime('%I:%M %p')
    hourly_weather_1_time = datetime.fromtimestamp(weather_response["hourly"]["data"][1]["time"]).strftime('%I:%M %p')
    #print (hourly_weather_0_time)
    
    current_summary = weather_response["currently"]["summary"]
    temp_hour_0 = round(weather_response["hourly"]["data"][0]["temperature"],1)
    temp_hour_1 = round(weather_response["hourly"]["data"][1]["temperature"],1)
    feels_temp_hour_0 = round(weather_response["hourly"]["data"][0]["apparentTemperature"],1)
    feels_temp_hour_1 = round(weather_response["hourly"]["data"][1]["apparentTemperature"],1)
   
    today_high_temp = round(weather_response["daily"]["data"][0]["temperatureHigh"],1)
    today_high_temp_time = datetime.fromtimestamp(weather_response["daily"]["data"][0]["temperatureHighTime"]).strftime('%I:%M %p')
    today_min_temp = round(weather_response["daily"]["data"][0]["temperatureLow"],1)
    today_low_temp_time = datetime.fromtimestamp(weather_response["daily"]["data"][0]["temperatureLowTime"]).strftime('%I:%M %p')

    next_hour_summary = weather_response["minutely"]["summary"]
    next_two_days_summary = weather_response["hourly"]["summary"]
    next_seven_days_summary = weather_response["daily"]["summary"]

    # synthesize the above into a one string that can be spoken
    spoken_weather = "\n" + \
            "Temperature at " + hourly_weather_0_time + " is " + str(temp_hour_0) + ". " + \
            "Feels like: " + str(feels_temp_hour_0) + ".\n" + \
            "At " + hourly_weather_1_time + " it will be " + str(temp_hour_1) + ". " + \
            "Feels like: " + str(feels_temp_hour_1) + ".\n" + \
            "Today's high is: " + str(today_high_temp) + " at " + today_high_temp_time + ".\n" + \
            "Today's low is: " + str(today_min_temp) + " at " + today_low_temp_time

    return spoken_weather

def text_to_speech(data):
    # Instantiates a client
    client = texttospeech.TextToSpeechClient()

    # Set the text input to be synthesized
    synthesis_input = texttospeech.SynthesisInput(text=data)

    # Build the voice request
    voice = texttospeech.VoiceSelectionParams(
        language_code="en-GB", ssml_gender=texttospeech.SsmlVoiceGender.FEMALE
    )  

    # Select the type of audio file you want returned
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        speaking_rate=1.1
    )

    # Perform the text-to-speech request on the text input with the selected
    # voice parameters and audio file type
    response = client.synthesize_speech(
        input=synthesis_input, voice=voice, audio_config=audio_config
    )

    # The response's audio_content is binary.
    with open("output.wav", "wb") as out:
        # Write the response to the output file.
        out.write(response.audio_content)
        print('Audio content written to file "output.wav"')

    weather_speech = AudioSegment.from_wav("output.wav")
    play(weather_speech)

def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '--keywords',
        nargs='+',
        help='List of default keywords for detection. Available keywords: %s' % ', '.join(sorted(pvporcupine.KEYWORDS)),
        choices=sorted(pvporcupine.KEYWORDS),
        metavar='')

    parser.add_argument(
        '--keyword_paths',
        nargs='+',
        help="Absolute paths to keyword model files. If not set it will be populated from `--keywords` argument")

    parser.add_argument('--library_path', help='Absolute path to dynamic library.', default=pvporcupine.LIBRARY_PATH)

    parser.add_argument(
        '--model_path',
        help='Absolute path to the file containing model parameters.',
        default=pvporcupine.MODEL_PATH)

    parser.add_argument(
        '--sensitivities',
        nargs='+',
        help="Sensitivities for detecting keywords. Each value should be a number within [0, 1]. A higher " +
             "sensitivity results in fewer misses at the cost of increasing the false alarm rate. If not set 0.5 " +
             "will be used.",
        type=float,
        default=None)

    parser.add_argument('--audio_device_index', help='Index of input audio device.', type=int, default=None)

    parser.add_argument('--output_path', help='Absolute path to recorded audio for debugging.', default=None)

    parser.add_argument('--show_audio_devices', action='store_true')

    args = parser.parse_args()

    if args.show_audio_devices:
        PorcupineDemo.show_audio_devices()
    else:
        if args.keyword_paths is None:
            if args.keywords is None:
                raise ValueError("Either `--keywords` or `--keyword_paths` must be set.")

            keyword_paths = [pvporcupine.KEYWORD_PATHS[x] for x in args.keywords]
        else:
            keyword_paths = args.keyword_paths

        if args.sensitivities is None:
            args.sensitivities = [0.5] * len(keyword_paths)

        if len(keyword_paths) != len(args.sensitivities):
            raise ValueError('Number of keywords does not match the number of sensitivities.')

        PorcupineDemo(
            library_path=args.library_path,
            model_path=args.model_path,
            keyword_paths=keyword_paths,
            sensitivities=args.sensitivities,
            output_path=args.output_path,
            input_device_index=args.audio_device_index).run()


if __name__ == '__main__':
    main()
