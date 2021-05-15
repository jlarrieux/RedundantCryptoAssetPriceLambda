import datetime
from typing import Tuple


def format_numbers(value: float, dec=2) -> str:
    formating_string = "{:,." + f'{dec}' + "f}"
    return formating_string.format(value)


def string_datetime_to_datetime_object(string_datetime: dict) -> datetime:
    date, time = string_datetime.rsplit(" ")
    year, month, day = get_3_ints(date, "-")
    hour, minute, second = get_3_ints(time, ":")
    return datetime.datetime(year, month=month, day=day, hour=hour, minute=minute, second=second)


def get_3_ints(value: str, separator: str) -> Tuple[int, int, int]:
    v1, v2, v3 = value.rsplit(separator)
    seconds = int(round(float(v3)))
    if seconds == 60:
        seconds = 59
    return int(v1), int(v2), seconds
