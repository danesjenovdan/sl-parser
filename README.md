# sl-parser

## run
```
pip install -r requirements.txt
python3 parser.py
```

## parser troubleshooting

### speeches

1. in parse_speeches.py set `DEBUG = True`
2. run python shell
3. ```
    from parlaparser.parse_speeches import *
    speech_parser = SpeechParser(None, [TEST_TRANSCRIPT_URL], None, None)
    speech_parser.parse()
   ```
4. make chages and repeat 3.


:bulb:

>If in parladata parsed person with weird name, for example like beginning of the law, you can add this weird words to `parlaparser.parse_speeches.SpeechParser.is_valid_name.forbiden_name_words`


