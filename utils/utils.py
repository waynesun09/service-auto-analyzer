"""
* Copyright 2019 EPAM Systems
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
* http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
"""

import re
import string
import nltk
import logging
from dateutil.parser import parse
import urllib

logger = logging.getLogger("analyzerApp.utils")
file_extensions = ["java", "php", "cpp", "cs", "c", "h", "js", "swift", "rb", "py", "scala"]


def sanitize_text(text):
    """Sanitize text by deleting all numbers"""
    return re.sub(r"\d+", "", text)


def calculate_line_number(text):
    """Calculate line numbers in the text"""
    return len([line for line in text.split("\n") if line.strip() != ""])


def first_lines(log_str, n_lines):
    """Take n first lines"""
    return "\n".join((log_str.split("\n")[:n_lines])) if n_lines >= 0 else log_str


def build_url(main_url, url_params):
    """Build url by concating url and url_params"""
    return main_url + "/" + "/".join(url_params)


def delete_empty_lines(log):
    """Delete empty lines"""
    return "\n".join([line for line in log.split("\n") if line.strip() != ""])


def reverse_log(log):
    """Concatenates lines in reverse order"""
    return "\n".join(log.split("\n")[::-1])


def split_words(text, min_word_length=0, only_unique=True, split_urls=True):
    all_unique_words = set()
    all_words = []
    stopwords = set(nltk.corpus.stopwords.words("english"))
    replace_symbols = r"[<>\{:,!?\}\[\];=\(\)\'\"]|\.\.\."
    text = re.sub(replace_symbols, " ", text)
    res = text.split()
    translate_map = {}
    for punct in string.punctuation:
        if punct != "." and (split_urls or punct not in ["/", "\\"]):
            translate_map[punct] = " "
    for word_part in res:
        word_part = re.sub(r"\s+", " ",
                           word_part.translate(word_part.maketrans(translate_map))).strip().lower()
        word_part = re.sub(r"\.+\b|\b\.+", "", word_part)
        for w in word_part.split():
            if w != "" and w not in stopwords and len(w) >= min_word_length and re.search(r"\w", w):
                if not only_unique or w not in all_unique_words:
                    all_words.append(w)
                    all_unique_words.add(w)
    return all_words


def find_query_words_count_from_explanation(elastic_res, field_name="message"):
    """Find information about matched words in elasticsearch query"""
    index_query_words_details = None
    all_words = set()
    try:
        for idx, field in enumerate(elastic_res["_explanation"]["details"]):
            if "weight(%s:" % field_name in field["description"].lower():
                word = re.search(r"weight\(%s:(.+) in" % field_name, field["description"]).group(1)
                all_words.add(word)
                break
            for detail in field["details"]:
                if "weight(%s:" % field_name in detail["description"].lower():
                    index_query_words_details = idx
                    break
        if index_query_words_details is not None:
            field_explaination = elastic_res["_explanation"]["details"]
            for detail in field_explaination[index_query_words_details]["details"]:
                word = re.search(r"weight\(%s:(.+) in" % field_name, detail["description"]).group(1)
                all_words.add(word)
    except Exception as e:
        logger.error(e)
        return []
    return list(all_words)


def transform_string_feature_range_into_list(text):
    """Converts features from string to list of ids"""
    values = []
    for part in text.split(","):
        if part.strip() == "":
            continue
        if "-" in part:
            start, end = part.split("-")[:2]
            values.extend(list(range(int(start), int(end) + 1)))
        else:
            values.append(int(part))
    return values


def remove_starting_datetime(text, remove_first_digits=False):
    """Removes datetime at the beginning of the text"""
    log_date = ""
    idx_text_start = 0
    for idx, str_part in enumerate(text.split(" ")):
        try:
            parse(log_date + " " + str_part)
            log_date = log_date + " " + str_part
            log_date = log_date.strip()
        except Exception as e: # noqa
            idx_text_start = idx
            break
    log_date = log_date.replace("'", "").replace("\"", "")
    if re.search(r"\d{1,7}", log_date) and re.search(r"\d{1,7}", log_date).group(0) == log_date:
        idx_text_start = 0

    text_split = text.split(" ")
    if remove_first_digits:
        if idx_text_start == 0:
            for idx in range(len(text_split)):
                rs = text_split[idx].translate(text_split[idx].maketrans("", "", string.punctuation))
                if not re.search(r"\d+", rs.strip()):
                    idx_text_start = idx
                    break

    return " ".join(text_split[idx_text_start:])


def delete_line_numbers(text):
    """Deletes line numbers in the stacktrace"""
    pattern_part = "|".join([r"(?<=\.%s:)" % ext for ext in file_extensions])
    text = re.sub(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}):(\d+)", r"\g<1>#\g<2>", text)

    res = re.sub(r"(?<=:)\d+(?=\)?\]?(\n|\r\n|$))", " ", text)
    res = re.sub(r"((?<=line )|(?<=line))\s*\d+\s*((?=, in)|(?=,in)|(?=\n)|(?=\r\n)|(?=$))",
                 " ", res, flags=re.I)
    res = re.sub(r"(%s)\s*\d+" % pattern_part, " ", res, flags=re.I)
    res = re.sub(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})#(\d+)", r"\g<1>:\g<2>", res)
    return res


def find_only_numbers(detected_message_with_numbers):
    """Removes all non digit symbols and concatenates unique numbers"""
    detected_message_only_numbers = re.sub(r"[^\d ]", "", detected_message_with_numbers)
    return " ".join(split_words(detected_message_only_numbers, only_unique=True))


def is_python_log(log):
    """Tries to find whether a log was for the python language"""
    found_file_extensions = []
    for file_extension in file_extensions:
        if re.search(r".\.%s\b" % file_extension, log):
            found_file_extensions.append(file_extension)
    if len(found_file_extensions) == 1 and found_file_extensions[0] == "py":
        return True
    return False


def detect_log_description_and_stacktrace(message, default_log_number=2,
                                          max_log_lines=10, choose_by_algorythm=False):
    """Split a log into a log message and stacktrace"""
    message = delete_empty_lines(message)
    if default_log_number == -1:
        return message, ""
    if calculate_line_number(message) > 2:
        is_python = is_python_log(message)
        if is_python:
            message = reverse_log(message)
        log_message_lines = -1
        for idx, line in enumerate(message.split("\n")):
            modified_line = delete_line_numbers(line)
            if modified_line != line:
                log_message_lines = idx
                break
        if log_message_lines < default_log_number:
            log_message_lines = default_log_number
        if log_message_lines == calculate_line_number(message):
            log_message_lines = max_log_lines
        if not choose_by_algorythm:
            if log_message_lines > max_log_lines:
                log_message_lines = max_log_lines
        log_message = first_lines(message, log_message_lines)
        stacktrace = "\n".join(message.split("\n")[log_message_lines:])
        if is_python:
            return reverse_log(log_message), reverse_log(stacktrace)
        return log_message, stacktrace
    return message, ""


def fix_big_encoded_urls(message):
    """Decodes urls encoded with %12 and etc. and removes brackets to separate url"""
    try:
        new_message = urllib.parse.unquote(message)
    except: # noqa
        pass
    if new_message != message:
        return re.sub(r"[\(\)\{\}#%]", " ", new_message)
    return message
