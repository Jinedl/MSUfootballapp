# Импортировать нужные библиотеки
from google.colab import files
import numpy as np
import pandas as pd
import plotly.figure_factory as ff
from matplotlib.backends.backend_agg import FigureCanvasAgg
import gspread
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageChops
import requests
from urllib.parse import urlencode
from bs4 import BeautifulSoup


# Преобразования входных данных
def ds_input(input_, ds_type, alternative=False):
    # Создание источника данных для ds_type
    data_types = {'timetable': GetTimetable, 'picture': GetPicture, 'font': GetFont,
                  'shortname': GetShortname, 'tournament_table': GetTournamentTable, 'code': GetTournamentCode}
    data_sources = {'Google Таблица': GoogleSpreadsheet, 'Загрузить вручную': GoogleColabInput, 'football.msu.ru': FootballMSUSite}
    input_ = input_.split('/')
    Data = data_types[ds_type]
    Source = data_sources[input_[0]]
    return Data(Source(*input_[1:], alternative=alternative))


def dates_input(input_):
    # Создание списка дат в формате дд.мм из списка дат формата гг-мм-дд
    dates = []
    for d in input_:
        if d != '':
            d = d.split('-')
            dates.append(f'{d[2]}.{d[1]}')
    return dates


def tournaments_input(input_):
    # Создание списка турниров из списка элементов формата номер_турнира и списка элементов формата (bool, [список дивизионов])
    all_tournaments = ['Стыки', 'ОПК', 'ЧВ', 'КР', 'МКР', 'ЛП', 'КП', 'ЗЛ']
    tournaments = []
    for i in range(len(input_)):
        if input_[i][0]:
            all_tournaments[i] = f'{input_[i][1]} {all_tournaments[i]}'
            if input_[i][2]:
                tournaments += list(map(lambda x: f'{all_tournaments[i]} {x}', input_[i][2].split()))
            else:
                tournaments.append(all_tournaments[i])
    return tournaments


def video_types_input(input_):
    # Создание списка типов видео
    all_video_types = ['Прямая трансляция', 'Полный матч', 'Обзор']
    video_types = []
    for i in range(len(input_)):
        if input_[i]:
            video_types.append(all_video_types[i])
    return video_types


def digits_arabic_to_roman(num):
    # Перевод числа из арабского формата в римский формат
    roman_dict = {1000: 'M', 900: 'CM', 500: 'D', 400: 'CD', 100: 'C', 90: 'XC',
                  50: 'L', 40: 'XL', 10: 'X', 9: 'IX', 5: 'V', 4: 'IV', 1: 'I'}
    roman_num = ''
    for key in roman_dict:
        while num >= key:
            roman_num += roman_dict[key]
            num -= key
    return roman_num


def date_to_str(m):
    # Преобразование даты к формату Д МЕСЯЦА из формата дд.мм
    months = ['ЯНВАРЯ', 'ФЕВРАЛЯ', 'МАРТА',
              'АПРЕЛЯ', 'МАЯ', 'ИЮНЯ',
              'ИЮЛЯ', 'АВГУСТА', 'СЕНТЯБРЯ',
              'ОКТЯБРЯ', 'НОЯБРЯ', 'ДЕКАБРЯ']
    m = list(map(int, m.split('.')))
    return f'{m[0]} {months[m[1]-1]}'


def weekday_to_str(wd):
    # Преобразование дня недели к формату ДЕНЬ из формата ДД
    weekdays = {'ПН': 'ПОНЕДЕЛЬНИК', 'ВТ': 'ВТОРНИК', 'СР': 'СРЕДА',
                'ЧТ': 'ЧЕТВЕРГ', 'ПТ': 'ПЯТНИЦА', 'СБ': 'СУББОТА', 'ВС': 'ВОСКРЕСЕНЬЕ'}
    return weekdays[wd.upper()]


def team_len(st):
    # Длина названия команд с учётом регистра названия
    length = 0
    for s in st:
        length += 1+s.isupper()*0.6
    return round(length+0.6)


def teams_to_match(home, guest, shortname_ds):
    # Создание противостояния команд вида ХОЗЯЕВА — ГОСТИ с длиной, подходящей к таблице
    if team_len(home+guest) > 32:

        home_shortname = shortname_ds.get_shortname(home)
        if home_shortname is None:
            home_shortname = home

        guest_shortname = shortname_ds.get_shortname(guest)
        if guest_shortname is None:
            guest_shortname = guest

        if team_len(home+guest_shortname) <= 32:
            guest = guest_shortname
        elif team_len(home_shortname+guest) <= 32:
            home = home_shortname
        else:
            home = home_shortname
            guest = guest_shortname

    return home+' — '+guest
# Векторизация функции по созданию противостояния
teams_to_match = np.vectorize(teams_to_match, excluded=['shortname_ds'], cache=True)


def tournament_to_caption(t):
    captions = {'опк': 'Чемпионат ОПК', 'стыки': 'Чемпионат ОПК', 'кр': 'Кубок Ректора', 'мкр': 'Кубок Ректора',
                'чв': 'Чемпионат Выпускников', 'лп': 'Летнее Первенство', 'кп': 'Кубок Первокурсника', 'зл': 'Зимняя Лига'}
    if type(t) == str:
        t = [t]
    tournaments = []
    for tt in t:
        tt = tt.split()
        tournaments.append(f'{digits_arabic_to_roman(int(tt[0]))} {captions[tt[1].strip().lower()]}')
    return ' x '.join(list(set(tournaments)) + ['msufootball'])


def subtournament_to_str(t, s):
    # для Высшего писать "В" кириллицей (в), для дивизиона "вэ" писать "B" латиницей (b)
    divisions = {'в': 'Высший', '1': 'Первый', '2': 'Второй', '3': 'Третий'}
    if t.lower().strip() in ['опк', 'чв', 'лп', 'зл']:
        if s.lower().strip() in divisions:
            return f'{divisions[s.lower().strip()]} дивизион'
        else:
            return f'Дивизион {s}'
    elif t.lower().strip() in ['кр', 'мкр', 'кп']:
        return f'Группа {s}'
    return s


def tournament_to_cover_text(t, s):
    # Получение полного подписи для обложки для видео в формате
    # Название турнира
    # Дивизион / Группа
    # Тур / Стадия
    # из формата "номер турнир дивизион", "стадия" (например, "13 ОПК 1В", "5")
    tournaments = {'опк': 'Чемпионат ОПК', 'стыки': 'Чемпионат ОПК', 'кр': 'Кубок Ректора', 'мкр': 'Малый Кубок Ректора',
                   'чв': 'Чемпионат Выпускников', 'лп': 'Летнее Первенство', 'кп': 'Кубок Первокурсника', 'зл': 'Зимняя Лига'}
    t = t.split()

    line1 = digits_arabic_to_roman(int(t[0])) + ' '
    th = t[1].lower().strip()
    if th in tournaments:
        line1 += tournaments[th]
    else:
        line1 += t[1]

    line2 = ''
    if len(t) == 3:
        if th in ['опк', 'чв', 'лп', 'зл', 'кр', 'мкр', 'кп']:
            line2 = subtournament_to_str(th, t[2])
        elif th == 'стыки':
            if t[2].lower().strip() == 'в':
                line2 = 'За Высший дивизион'
            elif t[2].strip() == '1':
                line2 = 'За Первый дивизион'
            elif t[2].strip() == '2':
                line2 = 'За Второй дивизион'
        else:
            line2 = t[2]

    line3 = ''
    if s.lower().strip() == 'ф':
        line3 = 'Финал'
    elif s.lower().strip() == '3 м':
        line3 = 'Матч за третье место'
    elif '/' in s:
        line3 = f'{s} финала'
    elif s.isdigit():
        line3 = f'{s} тур'
    else:
        line3 = s

    if not line2:
        line2 = line3
        line3 = ''

    return [line1, line2, line3]


def yadisk_to_url(url):
    # Получение ссылки для загрузки с Я.Диска
    base_url = 'https://cloud-api.yandex.net/v1/disk/public/resources/download?'
    final_url = base_url + urlencode(dict(public_key=url))
    response = requests.get(final_url)
    return response.json()['href']


def download_file(url):
    # Загрузка файла
    if 'yandex' in url.lower():
        url = yadisk_to_url(url)
    return requests.get(url).content


def make_timetable_picture(background_ds, font_ds, font, timetable_ds, dates, tournaments, shortname_ds):
    # Создание окончательной картинки с расписанием
    timetable_picture = background_ds.get_picture('vertical').resize((1280, 1280))
    big_font = font_ds.get_font(font, size=120)
    small_font = font_ds.get_font(font, size=30)

    draw = ImageDraw.Draw(timetable_picture)
    draw.text((110, 80), 'РАСПИСАНИЕ', font=big_font, fill='white')
    draw.text((110, 1130), tournament_to_caption(tournaments), font=small_font, fill='white')

    offset = 0
    for date in dates:
        timetable = timetable_ds.get_timetable(date)
        # if timetable.shape[0] == 0:
        #   pass
        timetable = timetable[(timetable['див'].str.lower().str.strip().str.contains('|'.join(tournaments).lower()) == True) &
                              # (timetable['див'].str.lower().str.strip().str.contains('резерв') == False) &
                              (timetable['счет'].str.lower().str.strip().str.contains('перенос') == False) &
                              (timetable['счет'].str.lower().str.strip().str.contains('тп') == False)].reset_index(drop=True).copy()

        date = date_to_str(date)
        weekday = timetable.loc[0, 'дн']
        weekday = weekday_to_str(weekday)
        time = timetable.loc[:, 'время']
        stadium = timetable.loc[:, 'поле']
        tournament = timetable.loc[:, 'див']
        teams = teams_to_match(timetable.loc[:, 'команда 1'].str.strip(), timetable.loc[:, 'команда 2'].str.strip(), shortname_ds)

        n = teams.shape[0]
        colorscale_white = [[0, '#ffffff'], [.5, '#ffffff'], [1, '#ffffff']]
        colorscale_red = [[0, '#620931'], [.5, '#620931'], [1, '#620931']]
        colorscale_green = [[0, '#183B19'], [.5, '#183B19'], [1, '#183B19']]

        datematch = [[f'{date} // {weekday}']]
        fig = ff.create_table(datematch, height_constant=60, colorscale=colorscale_red, index=True)
        fig.layout.annotations[0].font.size = 37
        fig.update_layout(width=1082, height=60)

        timetable_datematch = Image.open(BytesIO(fig.to_image(format="png")))
        timetable_picture.paste(timetable_datematch, (110, 284+offset))

        time = pd.DataFrame(time).values.tolist()
        fig = ff.create_table(time, height_constant=60, colorscale=colorscale_green, index=True)
        for i in range(len(fig.layout.annotations)):
            fig.layout.annotations[i].font.size = 37
        fig.update_layout(width=110, height=60*n)

        timetable_time = Image.open(BytesIO(fig.to_image(format="png")))
        timetable_picture.paste(timetable_time, (110, 284+offset+60+6))

        teams = pd.DataFrame(teams).values.tolist()
        fig = ff.create_table([['']] + teams, height_constant=60, colorscale=colorscale_white)
        for i in range(len(fig.layout.annotations)):
            fig.layout.annotations[i].font.size = 36
        fig.update_layout(width=662, height=60*(1+n))

        timetable_teams = Image.open(BytesIO(fig.to_image(format="png")))
        timetable_teams = timetable_teams.crop((22, 60, 662, timetable_teams.size[1]))
        timetable_picture.paste(timetable_teams, (110+110+6, 284+offset+60+6))

        info = pd.DataFrame(tournament+' // '+stadium).values.tolist()
        fig = ff.create_table(info, height_constant=60, colorscale=colorscale_green, index=True)
        for i in range(len(fig.layout.annotations)):
            fig.layout.annotations[i].font.size = 24
        fig.update_layout(width=320, height=60*n)

        timetable_info = Image.open(BytesIO(fig.to_image(format="png")))
        timetable_picture.paste(timetable_info, (110+110+6+640+6, 284+offset+60+6))

        offset += 60 + 6 + 60*n + 54

    return timetable_picture


def make_tournament_table(background_ds, font_ds, font, tournament_code_ds, tournament_table_ds, tournaments):
    # Создание окончательной картинки с турнирной таблицей
    picture = background_ds.get_picture('vertical').resize((1280, 1280))
    big_font = font_ds.get_font(font, size=90)
    small_font = font_ds.get_font(font, size=30)

    tournament_table_pictures = []
    for t in tournaments:

        tournament_code = tournament_code_ds.get_tournament_code(t)
        tournament_table = tournament_table_ds.get_tournament_table(tournament_code)
        stage = tournament_table['И'].mode().max()

        tournament_table_picture = picture.copy()

        div_types = {'в': 'ВЫСШИЙ', '1': 'ПЕРВЫЙ', '2': 'ВТОРОЙ', '3': 'ТРЕТИЙ'}
        dh = t.split()[2].lower()
        div = div_types[dh] if dh in div_types else dh.upper()

        draw = ImageDraw.Draw(tournament_table_picture)
        draw.text((110, 90), f'{div} // {stage} ТУР', font=big_font, fill='white')
        draw.text((110, 1140), tournament_to_caption(t), font=small_font, fill='white')

        teams = tournament_table.loc[:, 'Команда']
        values = tournament_table.loc[:, ['И', 'В', 'Н', 'П', 'МЗ', 'МП', 'О']]

        n = teams.shape[0]
        colorscale_values = [[0, '#620931'], [.5, '#ffffff'], [1, '#d9e3db']]
        colorscale_red = [[0, '#620931'], [.5, '#620931'], [1, '#620931']]
        colorscale_green = [[0, '#183B19'], [.5, '#183B19'], [1, '#183B19']]

        komanda = [['КОМАНДА']]
        fig = ff.create_table(komanda, height_constant=60, colorscale=colorscale_red, index=True)
        fig.layout.annotations[0].font.size = 36
        fig.update_layout(width=446, height=60)

        tournament_table_komanda = Image.open(BytesIO(fig.to_image(format="png")))
        tournament_table_picture.paste(tournament_table_komanda, (110, 284))

        teams = pd.DataFrame(teams).values.tolist()
        fig = ff.create_table(teams, height_constant=60, colorscale=colorscale_green, index=True)
        for i in range(len(fig.layout.annotations)):
            fig.layout.annotations[i].font.size = 36
        fig.update_layout(width=446, height=60*n)

        tournament_table_teams = Image.open(BytesIO(fig.to_image(format="png")))
        tournament_table_picture.paste(tournament_table_teams, (110, 284+60+6))

        fig = ff.create_table(values, height_constant=60, colorscale=colorscale_values)
        for i in range(len(fig.layout.annotations)):
            fig.layout.annotations[i].font.size = 36
        fig.update_layout(width=608, height=60*(1+n))

        tournament_table_values = Image.open(BytesIO(fig.to_image(format="png")))
        tournament_table_values = ImageChops.offset(tournament_table_values, 15, 0)
        tournament_table_values_cols = tournament_table_values.crop((0, 0, 608, 60))
        tournament_table_picture.paste(tournament_table_values_cols, (110+446+6, 284))
        tournament_table_values_vals = tournament_table_values.crop((0, 60, 608, 60*(1+n)))
        tournament_table_picture.paste(tournament_table_values_vals, (110+446+6, 284+60+6))

        tournament_table_pictures.append(tournament_table_picture)

    return tournament_table_pictures


def make_cover(background_ds, logo_ds, font_ds, font, video_types, team_1, team_2, text, tournament):
    # Создание обложки для видео
    cover = background_ds.get_picture('horizontal_rectangle').resize((1280, 720))
    vs_font = font_ds.get_font(font, size=100)
    big_font = font_ds.get_font(font, size=40)
    small_font = font_ds.get_font(font, size=25)
    logo_1 = logo_ds.get_picture(team_1).resize((240, 240))
    logo_2 = logo_ds.get_picture(team_2).resize((240, 240))

    mask = Image.new('L', (240, 240), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((5, 5, 235, 235), fill=255)

    draw = ImageDraw.Draw(cover)

    draw.text(
        (640-round(vs_font.getlength('VS')/2), 360-round(vs_font.getheight('VS')/2)),
        'VS',
        font=vs_font,
        fill='white')
    draw.text(
        (640-round(small_font.getlength(tournament_to_caption(tournament))/2), 610),
        tournament_to_caption(tournament),
        font=small_font,
        fill='white')

    draw.ellipse((190, 230, 190+260, 230+260), fill='white')
    cover.paste(logo_1, (190+10, 230+10), mask)
    draw.text(
        (190+260//2-round(big_font.getlength(team_1)/2), 230+260+20),
        team_1,
        font=big_font,
        fill='white')

    draw.ellipse((830, 230, 830+260, 230+260), fill='white')
    cover.paste(logo_2, (830+10, 230+10), mask)
    draw.text(
        (830+260//2-round(big_font.getlength(team_2)/2), 230+260+20),
        team_2,
        font=big_font,
        fill='white')

    draw.text(
        (640-round(small_font.getlength(text[0])/2), 180 + 0*(25+5)),
        text[0],
        font=small_font,
        fill='white')
    draw.text(
        (640-round(small_font.getlength(text[1])/2), 180 + 1*(25+5)),
        text[1],
        font=small_font,
        fill='white')
    draw.text(
        (640-round(small_font.getlength(text[2])/2), 180 + 2*(25+5)),
        text[2],
        font=small_font,
        fill='white')
    draw.text(
        (640-round(small_font.getlength(text[3])/2), 180 + 3*(25+5)),
        text[3],
        font=small_font,
        fill='white')

    covers = []
    for vd in video_types:
        cover_picture = cover.copy()
        draw_video_type = ImageDraw.Draw(cover_picture)
        draw_video_type.text((95, 100), vd.upper(), font=big_font, fill='white')
        covers.append(cover_picture)

    return covers


def make_many_covers(background_ds, logo_ds, font_ds, font, timetable_ds, video_types, dates):
    # Создание обложек из расписания с матчами
    covers = []
    for date in dates:
        timetable = timetable_ds.get_timetable(date)
        timetable = timetable[(timetable['видео'].isna() == False) &
                              (timetable['видео'] != '')].reset_index(drop=True).copy()

        date = date_to_str(date).lower()
        for i in timetable.index:
            team_1 = timetable.loc[i, 'команда 1'].strip()
            team_2 = timetable.loc[i, 'команда 2'].strip()
            text = [f'{date} {timetable.loc[i, "время"]}'] + tournament_to_cover_text(timetable.loc[i, 'див'], timetable.loc[i, 'тур'])
            tournament = timetable.loc[i, 'див']
            covers += make_cover(background_ds, logo_ds, font_ds, font, video_types, team_1, team_2, text, tournament)

    return covers


class GoogleAccount(object):
    # Класс синглтон для установления связи с google-api
    __instance = None
    __key = 'key.json'
    __ga = None

    def __new__(cls):
        if cls.__instance is None:
            cls.__instance = object.__new__(cls)
            cls.__ga = gspread.service_account(filename=cls.__key)
        return cls.__instance

    def __call__(self):
        return self.__ga


class DataSource(object):
    # Класс-родитель для источников данных
    def get_timetable(self):
        print('Из этого источника данных невозможно получить расписание')

    def get_picture(self):
        print('Из этого источника данных невозможно получить картинку')

    def get_tournament_table(self):
        print('Из этого источника данных невозможно получить турнирную таблицу')

    def get_shortname(self):
        print('Из этого источника данных невозможно получить сокращённое название команды')

    def get_font(self):
        print('Из этого источника данных невозможно получить почерк')

    def get_tournament_code(self):
        print('Из этого источника данных невозможно получить код турнира')


class GetTimetable(DataSource):
    # Класс для получения расписания из источника данных
    __ds = None
    __cache = {}

    def __init__(self, ds):
        self.__ds = ds

    def get_timetable(self, date):
        if date not in self.__cache:
            self.__cache[date] = self.__ds.get_timetable(date)
        return self.__cache[date]


class GetPicture(DataSource):
    # Класс для получения картинки из источника данных
    __ds = None
    __cache = {}

    def __init__(self, ds):
        self.__ds = ds

    def get_picture(self, key):
        if key not in self.__cache:
            self.__cache[key] = self.__ds.get_picture(key)
        return self.__cache[key]


class GetFont(DataSource):
    # Класс для получения почерка из источника данных
    __ds = None
    __cache = {}

    def __init__(self, ds):
        self.__ds = ds

    def get_font(self, key, size):
        if (key, size) not in self.__cache:
            self.__cache[(key, size)] = self.__ds.get_font(key, size)
        return self.__cache[(key, size)]


class GetShortname(DataSource):
    # Класс для получения сокращённого названия из источника данных
    __ds = None
    __cache = {}

    def __init__(self, ds):
        self.__ds = ds

    def get_shortname(self, team):
        if team not in self.__cache:
            self.__cache[team] = self.__ds.get_shortname(team)
        return self.__cache[team]


class GetTournamentTable(DataSource):
    # Класс для получения турнирной таблицы из источника данных
    __ds = None
    __cache = {}

    def __init__(self, ds):
        self.__ds = ds

    def get_tournament_table(self, tournament):
        if tournament not in self.__cache:
            self.__cache[tournament] = self.__ds.get_tournament_table(tournament)
        return self.__cache[tournament]


class GetTournamentCode(DataSource):
    # Класс для получения кода турнирна
    __ds = None
    __cache = {}

    def __init__(self, ds):
        self.__ds = ds

    def get_tournament_code(self, tournament):
        if tournament not in self.__cache:
            self.__cache[tournament] = self.__ds.get_tournament_code(tournament)
        return self.__cache[tournament]


class GoogleSpreadsheet(DataSource):
    # Класс для источника данных - google spreadsheet
    __ds = None
    __alternative = False

    def __init__(self, spreadsheet_name, worksheet_name, alternative=False):
        ga = GoogleAccount()
        self.__ds = ga().open(spreadsheet_name).worksheet(worksheet_name)
        self.__alternative = alternative

    def get_timetable(self, date):

        worksheet = self.__ds
        timetable = None
        try:
            cell_list = worksheet.findall(date.strip().lower())
            cell_list = list(map(lambda c: c.row, cell_list))
            timetable = []
            for cl in cell_list:
                timetable.append(worksheet.row_values(cl))
            columns = worksheet.row_values(1)
            timetable = pd.DataFrame(timetable)
            cols = timetable.shape[1]
            if cols < len(columns):
                columns = columns[:cols]
            else:
                columns += [''] * (cols-len(columns))
            timetable.columns = list(map(str.lower, map(str.strip, columns)))
        except:
            if self.__alternative:
                pass
        return timetable

    def get_picture(self, key):

        worksheet = self.__ds
        picture = None
        try:
            cell = worksheet.find(key.strip().lower())
            url = worksheet.cell(cell.row, cell.col+1).value
            buf = BytesIO(download_file(url))
            picture = Image.open(buf)
        except:
            if self.__alternative:
                alternative_ds = GetPicture(GoogleColabInput())
                picture = alternative_ds.get_picture(key)
        return picture

    def get_shortname(self, team):

        if team_len(team) <= 14:
            return team

        worksheet = self.__ds
        shortname = None
        try:
            cell = worksheet.find(team.strip().lower())
            shortname = worksheet.cell(cell.row, cell.col+1).value
        except:
            if self.__alternative:
                alternative_ds = GetShortname(GoogleColabInput())
                shortname = alternative_ds.get_shortname(team)
            else:
                shortname = team
        return shortname

    def get_font(self, key, size):

        worksheet = self.__ds
        font = None
        try:
            cell = worksheet.find(key.strip().lower())
            url = worksheet.cell(cell.row, cell.col+1).value
            buf = BytesIO(download_file(url))
            font = ImageFont.truetype(buf, size=size)
        except:
            if self.__alternative:
                alternative_ds = GetFont(GoogleColabInput())
                font = alternative_ds.get_font(key, size)
        return font

    def get_tournament_code(self, tournament):

        worksheet = self.__ds
        tournament_code = None
        try:
            cell = worksheet.find(tournament.strip().lower())
            tournament_code = worksheet.cell(cell.row, cell.col+1).value
        except:
            if self.__alternative:
                alternative_ds = GetTournamentCode(GoogleColabInput())
                tournament_code = alternative_ds.get_tournament_code(tournament)
        return tournament_code


class GoogleColabInput(DataSource):
    # Класс для источника данных - ввод в google colab
    def get_picture(self, key):
        if key == '':
            print(f'↓ Загрузи картинку')
        else:
            print(f'↓ Загрузи картинку "{key}" вручную, т.к. её нет в базе данных')
        picture = files.upload()
        buf = BytesIO(picture[list(picture.keys())[0]])
        return Image.open(buf)

    def get_font(self, key, size):
        worksheet = self.__ds
        if key == '':
            print(f'↓ Загрузи шрифт')
        else:
            print(f'↓ Загрузи шрифт "{key}" вручную, т.к. его нет в базе данных')
        font = files.upload()
        buf = BytesIO(font[list(font.keys())[0]])
        return ImageFont.truetype(buf, size=size)

    def get_shortname(self, team):
        return input(f'Введите сокращенное название для команды "{team}"\n')

    def get_tournament_code(self, tournament):
        return input(f'Введите код для турнира "{tournament}"\n')


class FootballMSUSite(DataSource):
    # Класс для источника данных - http://football.msu.ru
    __alternative = False

    def __init__(self, alternative=False):
        self.__alternative = alternative

    def get_tournament_table(self, code):
        tournament_table = None
        try:
            url = f'http://football.msu.ru/tournament/{code.split()[0]}/tables?round_id={code.split()[1]}'
            soup = BeautifulSoup(requests.get(url).text, 'lxml')
            table = soup.find('div', {'id': "tournamentTablesTable",
                              'class': "tournaments-tables-cont sfl-tab-cont mobile"}).find('table')
            rows = table.find_all('tr')
            columns = list(map(lambda x: x.text.strip(), rows[0].find_all('th')))[1:-1]
            teams = [list(map(lambda x: x.text.strip(), r.find_all('td')))[2:-1] for r in rows[1:]]
            tournament_table = pd.DataFrame(teams, columns=columns)
        except:
            if self.__alternative:
                pass
        return tournament_table
