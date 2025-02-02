import googletrans
from typing import List, Iterator
import logging
import re, time, sys
from translatesubs.translator.itranslator import ITranslator
from translatesubs.translator.language import Language
from translatesubs.translator.translated import Translated
from translatesubs.tools import nth

from pdb import set_trace

"""
The API has problems with pronunciations: 
1. cannot pronounce the original text and
2. cannot pronounce multiple sentences (pronunciation becomes None).

To extract correct pronunciation data, we can look at examples:

1) how are you? -> spanish (origin: cannot pronounce, translation: cannot pronounce)
[['¿cómo estás?', 'how are you?', None, None, 1]]
- if the last element is a number or is not a str, then there are NO translations

2) how are you? -> japanese (origin: cannot pronounce, translation: can pronounce)
[['お元気ですか？', 'how are you?', None, None, 1], [None, None, 'Ogenkidesuka?']]
original pronounced does not exist, translation pronounced [-1]
- if 1) is correct AND length of elements is <4, that means still cannot pronounce original 

3) お元気ですか？ -> english (origin: can pronounce, translation: cannot pronounce)
[['How are you?', 'お元気ですか？', None, None, 1], [None, None, None, 'Ogenkidesuka?']]
original pronounced [-1], translation pronounced is None
- if length >3 and -2 element is None, that means cannot pronounce translation

4) お元気ですか？ -> korean (origin: can pronounce, translation: can pronounce)
[['잘 지내?', 'お元気ですか？', None, None, 0], [None, None, 'jal jinae?', 'Ogenkidesuka?']]
original pronounced [-1], translation pronounced [-2]
- if 1) is correct AND

Logic:
1) If there is a translation AND len == 4, then there is origin language pronunciation at -1 index, else there isn't one
2) If there is a translation AND 2 index is not None, then there is a translation at 2 index, otherwise there isn't one
"""


class GoogleTrans(ITranslator):
    separator = " $$$ "
    separator_out = separator.replace(" ","")
    char_limit = 2000
    ifclean = "clean"
    def set_clean(self, ifclean: str) -> None:
        self.ifclean = ifclean

    def get_char_limit(self) -> int:
        return self.char_limit

    def set_char_limit(self, char_limit: int) -> None:
        self.char_limit = char_limit

    def set_separator(self, separator: str) -> None:
        self.separator = separator
        self.separator_out = separator.replace(" ","")

    def clean_space_in_separator(self, tmpo: List[str], text0: str) -> str:
        separator, separator_out = self.separator, self.separator_out
        nori = len(tmpo)
        text0 = text0.strip()
        text = text0
        if self.ifclean == "no":
            return text
        if len(separator_out) > 1:
            if len(text.split(separator)) == nori:
                return text
            else:
                for to_clean in set([ ' ' + separator_out[0] + ' ', ' ' + separator_out[-1] + ' ', ' ' + separator_out[:2] + ' ' ]):
                    text = text.replace(to_clean,separator_out)
                if len(text.split(separator)) == nori:
                    return text
                else:
                    return text0
#                if not len(text1) == len(text):
#                    print(text,"XXXX\n\nXXXX",text1)
#                    text = text1
            return text
        else:
            return text

    def trynarrowdown(self, tmpo: List[str], to_lang: str):
        separator, separator_out = self.separator, self.separator_out
        tmpt_out, nogoods = [], []
        isep = int(len(tmpo)/2)
        if isep > 2:
            tmpo_left = tmpo[:isep]
            tmpo_left_str = separator.join(tmpo_left)
            tmpt_left_str = self.clean_space_in_separator(tmpo_left,self._do_translate(tmpo_left_str, to_lang).text)
            tmpt = tmpt_left_str.split(separator_out)
            if len(tmpt) == len(tmpo_left):
                tmpt_out += tmpt
            else:
#                print("left",len(tmpt),isep,tmpo_left_str,tmpt_left_str)
                tmpt, nogood = self.trynarrowdown(tmpo_left, to_lang)
                tmpt_out += tmpt
                nogoods += nogood
            tmpo_right = tmpo[isep:]
            tmpo_right_str = separator.join(tmpo_right)
            tmpt_right_str = self.clean_space_in_separator(tmpo_right,self._do_translate(tmpo_right_str, to_lang).text)
            tmpt = tmpt_right_str.split(separator_out)
            if len(tmpt) == len(tmpo_right):
                tmpt_out += tmpt
            else:
#                print("right",len(tmpt),isep,tmpo_right_str,tmpt_right_str)
                tmpt, nogood = self.trynarrowdown(tmpo_right, to_lang)
                tmpt_out += tmpt
                nogoods += nogood
        else:
            tmpo_left = tmpo
            tmpo_left_str = separator.join(tmpo_left)
            tmpt_left_str = self.clean_space_in_separator(tmpo_left,self._do_translate(tmpo_left_str, to_lang).text)
            tmpt = tmpt_left_str.split(separator_out)
            n_nogood = len(tmpo_left) - len(tmpt)
            tmpt_out += tmpt + [ "" ] * (n_nogood)
            nogoods += tmpo_left
        time.sleep(0.2)
#        if not len(tmpt_out) == len(tmpo):
#            set_trace()
        print(f"###trynarrowdown: ",len(tmpt_out), len(tmpo), nogoods)
        return tmpt_out, nogoods
            
    def translate(self, text: List[str], to_lang: str, iftrynarrow = "try") -> Iterator[Translated]:
        separator, separator_out = self.separator, self.separator_out
        google_translated = GoogleTrans._do_translate(text, to_lang)
        for original, translated in zip(text, google_translated):
            if iftrynarrow == 'try' and len(separator):
                tmpo = original.split(separator)
                if len(tmpo) > 1:
                    tmpt = self.clean_space_in_separator(tmpo,translated.text).split(separator_out)
                    if not len(tmpo) == len(tmpt):
                        tmpt_out, nogood = self.trynarrowdown(tmpo, to_lang)
                        translated.text = separator.join(tmpt_out).strip()
            yield Translated(original=original,
                             translated=translated.text,
                             pronounce_original=GoogleTrans._pronounce_origin(translated),
                             pronounce_translated=GoogleTrans._pronounce_translated(translated))

    def detect_language(self, to_lang: str) -> Language:
        return next((Language(full, abb) for abb, full in googletrans.LANGUAGES.items()
                     if to_lang == abb or to_lang == full), None)

    def get_supported(self) -> str:
        return ', '.join([f'{abb} - {full}' for abb, full in googletrans.LANGUAGES.items()])

    @staticmethod
    def _do_translate(text: List[str], to_lang: str) -> List[googletrans.models.Translated]:
        """
        Call google translate API to translate given text

        :param **kwargs:
        :param text: The source text(s) to be translated. Batch translation is supported via sequence input.
        :type text: UTF-8 :class:`str`; :class:`unicode`; string sequence (list, tuple, iterator, generator)

        :return: translated text in the same form it was provided
        """
        # Google API provider should allow new access every 1h, but if more translations need to be done,
        # a number of different country providers are given
        # E.g. from here https://sites.google.com/site/tech4teachlearn/googleapps/google-country-codes
        # But have to make sure the site actually loads first :)

        ending_formula = re.compile(r'translate\..*?\.(.+)$')  # for for com, co.uk, lt or others
        provider_endings = (ending_formula.search(url).group(1) for url in googletrans.constants.DEFAULT_SERVICE_URLS)
        provider_base = 'translate.googleapis'

        for ending in provider_endings:
            provider = f'{provider_base}.{ending}'
            translator = googletrans.Translator(service_urls=[provider])
            try:
                return translator.translate(text, dest=to_lang)
            except AttributeError:
                logging.info(f'Provider "{provider}" got blocked, trying another one...')
        exit('No more providers left to try, try updating the provider list or wait 1h until you get unblocked.')

    @staticmethod
    def _pronounce_origin(translated: googletrans.models.Translated) -> str:
        # The only way we have origin pronunciation is when extra_data['translation'] contains at least two items:
        # 1) translation and 2) pronunciation. The latter must then contain 4 items, while the last item is the origin
        # translation. If the pronunciation only contains 3 items, then the 3rd item is the pronounced translation.
        expected = GoogleTrans._expected_pronounced(translated)
        if GoogleTrans._can_pronounce(expected) and GoogleTrans._can_pronounce_original(expected):
            return expected[-1]
        return translated.origin

    @staticmethod
    def _pronounce_translated(translated: googletrans.models.Translated) -> str:
        # When returning pronunciation of translated, the API returns pronunciation whenever one is available.
        # If however, it is not available it returns original text, while I would want it to return the translated text
        # instead, since that simply means that the text is already pronounced.
        expected = GoogleTrans._expected_pronounced(translated)
        if GoogleTrans._can_pronounce(expected) and GoogleTrans._can_pronounce_translated(expected):
            return expected[2]
        return translated.text

    @staticmethod
    def _expected_pronounced(translated: googletrans.models.Translated) -> List:
        return nth(translated.extra_data['translation'], -1)

    @staticmethod
    def _can_pronounce(pronounced: List) -> bool:
        return isinstance(nth(pronounced, -1), str)

    @staticmethod
    def _can_pronounce_original(pronounced: List) -> bool:
        return len(pronounced) == 4

    @staticmethod
    def _can_pronounce_translated(pronounced: List) -> bool:
        return pronounced[2] is not None
