import pyttsx3
import sys

def falar(texto):
    engine = pyttsx3.init()
    engine.setProperty('rate', 200)
    voices = engine.getProperty('voices')
    for voice in voices:
        if "brazil" in voice.name.lower():
            engine.setProperty('voice', voice.id)
            break
    engine.say(texto)
    engine.runAndWait()

if __name__ == "__main__":
    if len(sys.argv) > 1:
        falar(sys.argv[1])