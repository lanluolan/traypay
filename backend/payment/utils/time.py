from datetime import datetime


def getDate(date_str=None):
    if not date_str:
        today = datetime.today()
        return today.year, today.month, today.day
    date = datetime.strptime(date_str, '%Y-%m-%d')
    return date.year, date.month, date.day
