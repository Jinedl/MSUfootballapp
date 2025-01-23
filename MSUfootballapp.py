# Импортировать нужные библиотеки
import numpy as np
import pandas as pd
import gspread
import plotly.figure_factory as ff
import re
import requests
from matplotlib.backends.backend_agg import FigureCanvasAgg
from google.colab import files
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageChops
from urllib.parse import urlencode
from bs4 import BeautifulSoup


# Преобразования входных данных
def ds_input(input_, ds_type, alternative=False):
    # Создание источника данных для ds_type
    data_types = {'timetable': GetTimetable, 'picture': GetPicture, 'font': GetFont,
                  'shortname': GetShortname, 'tournament_table': GetTournamentTable, 'code': GetTournamentCode}
    data_sources = {'Google Таблица': GoogleSpreadsheet, 'Загрузить вручную': GoogleColabInput, 'football.msu.ru': FootballMSUSiteOld, 'footballmsu.ru': FootballMSUSite}
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
    # Создание списка турниров из списка элементов формата (bool, номер_турнира, турнир_подтурниры_через_пробел)
    all_tournaments = ['Стыки', 'ОПК', '8x8', 'КЧ', 'ЧВ', 'КР', 'МКР', 'ЛП', 'КП', 'ЗЛ']
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


def players_input(input_):
    # Создание отсортированного списка непустых игроков
    positions_num = {"ВРТ": 0, "ЛЗ": 1, "ЛЦЗ": 2, "ЦЦЗ": 3, "ПЦЗ": 4, "ПЗ": 5,
                     "ЛП": 6, "ЛЦП": 7, "ЦЦП": 8, "ПЦП": 9, "ПП": 10,
                     "ЛН": 11, "ЛЦН": 12, "ЦЦН": 13, "ПЦН": 14, "ПН": 15}
    players = []
    for p in input_:
        if p[0]:
            players.append(p)
    players = sorted(players, key=lambda x: positions_num[x[-1]])
    players = tuple(tuple(pl for pl in players if pl[-1][-1] == pos) for pos in ['Т', 'З', 'П', 'Н'])
    return players


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
    # Длина названия команд с учётом регистра символов
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
    # Получение подписи с номером и названием турнира
    captions = {'опк': 'Чемпионат ОПК', 'стыки': 'Чемпионат ОПК', '8x8': 'Лига 8x8', 'кч': 'Клубный Чемпионат', 'кр': 'Кубок Ректора', 'мкр': 'Малый Кубок Ректора',
                'чв': 'Чемпионат Выпускников', 'лп': 'Летнее Первенство', 'кп': 'Кубок Первокурсника', 'зл': 'Зимняя Лига'}
    if type(t) == str:
        t = [t] if t else []
    tournaments = []
    for tt in t:
        tt = tt.split()
        tournaments.append(f'{digits_arabic_to_roman(int(tt[0]))} {captions[tt[1].strip().lower()]}')
    return ' x '.join(list(set(tournaments)) + ['msufootball'])


def subtournament_to_str(t, s):
    # Получение полного названия подтурнира (дивизиона или группы)
    # Для Высшего писать "В" кириллицей (в), для дивизиона "вэ" писать "B" латиницей (b)
    divisions = {'в': 'Высший', '1': 'Первый', '2': 'Второй', '3': 'Третий'}
    if t.lower().strip() in ['опк', '8x8', 'кч', 'чв', 'лп', 'зл']:
        if s.lower().strip() in divisions:
            return f'{divisions[s.lower().strip()]} дивизион'
        else:
            return f'Дивизион {s}'
    elif t.lower().strip() in ['кр', 'мкр', 'кп']:
        return f'Группа {s}'
    return s


def tournament_to_cover_text(t, s):
    # Получение полной подписи для обложки для видео в формате
    # Название турнира
    # Дивизион / Группа
    # Тур / Стадия
    # из формата "номер турнир дивизион", "стадия" (например, "13 ОПК 1В", "5")
    tournaments = {'опк': 'Чемпионат ОПК', 'стыки': 'Чемпионат ОПК', '8x8': 'Лига 8x8', 'кч': 'Клубный Чемпионат', 'кр': 'Кубок Ректора', 'мкр': 'Малый Кубок Ректора',
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
        if th in ['опк', '8x8', 'кч', 'чв', 'лп', 'зл', 'кр', 'мкр', 'кп']:
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
    timetable_picture = background_ds.get_picture('vertical')
    width, height = timetable_picture.size
    height *= 1280 // width
    timetable_picture = timetable_picture.resize((1280, height))

    big_font = font_ds.get_font(font).font_variant(size=120)
    small_font = font_ds.get_font(font).font_variant(size=30)

    draw = ImageDraw.Draw(timetable_picture)
    draw.text((110, 80), 'РАСПИСАНИЕ', font=big_font, fill='white')
    draw.text((110, height-150), tournament_to_caption(tournaments), font=small_font, fill='white')

    offset = 0
    for date in dates:
        timetable = timetable_ds.get_timetable(date)
        # if timetable.shape[0] == 0:
        #   pass
        timetable = timetable[(timetable['див'].str.lower().str.strip().str.contains('|'.join(tournaments).lower()) == True) &
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
            fig.layout.annotations[i].font.size = 22
        fig.update_layout(width=320, height=60*n)

        timetable_info = Image.open(BytesIO(fig.to_image(format="png")))
        timetable_picture.paste(timetable_info, (110+110+6+640+6, 284+offset+60+6))

        offset += 60 + 6 + 60*n + 54

    return timetable_picture


def make_tournament_table_picture(background_ds, font_ds, font, tournament_code_ds, tournament_table_ds, tournaments):
    # Создание окончательной картинки с турнирной таблицей
    picture = background_ds.get_picture('vertical')
    width, height = picture.size
    height *= 1280 // width
    picture = picture.resize((1280, height))

    big_font = font_ds.get_font(font).font_variant(size=60)
    small_font = font_ds.get_font(font).font_variant(size=30)
    tournament_codes = []
    for t in tournaments:
        tournament_codes += tournament_code_ds.get_tournament_code(t)
    tournament_table_pictures = []
    for tc in tournament_codes:

        tournament_table = tournament_table_ds.get_tournament_table(tc)
        tournament = tournament_table.index.name
        # stage = tournament_table['И'].mode().max() # Число игр

        tournament_table_picture = picture.copy()

        draw = ImageDraw.Draw(tournament_table_picture)
        draw.text((110, 120), tournament.upper(), font=big_font, fill='white')
        draw.text((110, height-140), tournament_to_caption(t), font=small_font, fill='white')

        teams = tournament_table.loc[:, 'Команда']
        values = tournament_table.loc[:, ['И', 'В', 'Н', 'П', 'МЗ', 'МП', 'О']]

        n = teams.shape[0]
        colorscale_values = [[0, '#620931'], [.5, '#ffffff'], [1, '#d9e3db']]
        colorscale_red = [[0, '#620931'], [.5, '#620931'], [1, '#620931']]
        colorscale_green = [[0, '#183B19'], [.5, '#183B19'], [1, '#183B19']]

        komanda = [['КОМАНДА']]
        fig = ff.create_table(komanda, height_constant=60, colorscale=colorscale_red, index=True)
        fig.layout.annotations[0].font.size = 36
        fig.update_layout(width=474, height=60)

        tournament_table_komanda = Image.open(BytesIO(fig.to_image(format="png")))
        tournament_table_picture.paste(tournament_table_komanda, (110, 284))

        teams = pd.DataFrame(teams).values.tolist()
        fig = ff.create_table(teams, height_constant=60, colorscale=colorscale_green, index=True)
        for i in range(len(fig.layout.annotations)):
            fig.layout.annotations[i].font.size = 36
        fig.update_layout(width=474, height=60*n)

        tournament_table_teams = Image.open(BytesIO(fig.to_image(format="png")))
        tournament_table_picture.paste(tournament_table_teams, (110, 284+60+6))

        fig = ff.create_table(values, height_constant=60, colorscale=colorscale_values)
        for i in range(len(fig.layout.annotations)):
            fig.layout.annotations[i].font.size = 36
        fig.update_layout(width=580, height=60*(1+n))

        tournament_table_values = Image.open(BytesIO(fig.to_image(format="png")))
        tournament_table_values = ImageChops.offset(tournament_table_values, 15, 0)
        tournament_table_values_cols = tournament_table_values.crop((0, 0, 580, 60))
        tournament_table_picture.paste(tournament_table_values_cols, (110+474+6, 284))
        tournament_table_values_vals = tournament_table_values.crop((0, 60, 580, 60*(1+n)))
        tournament_table_picture.paste(tournament_table_values_vals, (110+474+6, 284+60+6))

        tournament_table_pictures.append(tournament_table_picture)

    return tournament_table_pictures


def make_cover(background_ds, logo_ds, font_ds, font, video_types, team_1, team_2, text, tournament):
    # Создание обложки для видео
    cover = background_ds.get_picture('horizontal_rectangle').resize((1280, 720))
    vs_font = font_ds.get_font(font).font_variant(size=100)
    big_font = font_ds.get_font(font).font_variant(size=40)
    small_font = font_ds.get_font(font).font_variant(size=25)
    logo_1 = logo_ds.get_picture(team_1).resize((240, 240))
    logo_2 = logo_ds.get_picture(team_2).resize((240, 240))

    mask = Image.new('L', (240, 240), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse((5, 5, 235, 235), fill=255)

    draw = ImageDraw.Draw(cover)

    draw.text(
        (640 - vs_font.getlength('VS')//2, 300),
        'VS',
        font=vs_font,
        fill='white')
    draw.text(
        (640 - small_font.getlength(tournament_to_caption(tournament))//2, 610),
        tournament_to_caption(tournament),
        font=small_font,
        fill='white')

    draw.ellipse((190, 230, 190+260, 230+260), fill='white')
    cover.paste(logo_1, (190+10, 230+10), mask)
    draw.text(
        (190 + 260//2 - big_font.getlength(team_1)//2, 230+260+20),
        team_1,
        font=big_font,
        fill='white')

    draw.ellipse((830, 230, 830+260, 230+260), fill='white')
    cover.paste(logo_2, (830+10, 230+10), mask)
    draw.text(
        (830 + 260//2 - big_font.getlength(team_2)//2, 230+260+20),
        team_2,
        font=big_font,
        fill='white')

    draw.text(
        (640 - small_font.getlength(text[0])//2, 180 + 0*(25+5)),
        text[0],
        font=small_font,
        fill='white')
    draw.text(
        (640 - small_font.getlength(text[1])//2, 180 + 1*(25+5)),
        text[1],
        font=small_font,
        fill='white')
    draw.text(
        (640 - small_font.getlength(text[2])//2, 180 + 2*(25+5)),
        text[2],
        font=small_font,
        fill='white')
    draw.text(
        (640 - small_font.getlength(text[3])//2, 180 + 3*(25+5)),
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


def make_player_picture(font_ds, font, player_ds, player, text, goals, assists):
    # Содание картинки игрока
    mark_goal_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x1a\x00\x00\x00\x1a\x08\x06\x00\x00\x00\xa9JL\xce\x00\x00\x02\xa7IDATx\x9c\x95\x96M\x88Na\x14\xc7\x7f\xf7\xf5Q\xc4\x0c\xca\x88\x94B\xcdN\xd6L(25\x13\xf9\xd8\x90\xa5\xad\x85\x85&\x1b\xc5\x8e\x08K\x8ab-d1E\xc9\xc7\xcc\xc8\xc7\x02c\xc1\x06M>\xb2P\x8c\t\xcd\x98\xcc\xcf\xe2\x9e\x97\xdb\xf5\xde\xe7\xf2\xaf\xb3x\xef\xf3?\xffs\x9e\xe79\xe7<oF\x02\xea4\xa0\x0b\xd8\x06\xac\x03\x96\x03scy\x0cx\r\x0c\x00\xd7\x80\xc1,\xcb\xa6RzUA\xb6\xaa7\xd4\xaf\xd6cL\xbd\xaen\xf9\x9f\x00\xed\xeaE\xf5\x96\xbaQ]\xad\x1eW_\xb7\x08\xf0J=\xaa\xae\n\xee-\xf5\x82\xda^\x17d\x89zO=\xa6\xce,\xad\xcdSw\xabO\xc3v\x95\x05\xd5\x99\xe1;\xa8.N\xeddH\xdd_\x93\xcc!\xf5P\rg\x7f\x04\xfb\x9dH\xa3\xb0~\x92\xfcBO\xa7D\x80\xe9a\x95\x08\x8d!\xe0D9\x83n\xf5\x8b\xdaQ\x13\x04\xf5\x88z\xe4\x1fx\x1d\xa1\xb9\x19\xa0\x11%|\x10h\x03:\xeb\x04\x80\x9fau\xe8\x0c\xcd\x83\xea4\xd4.u2\xaa\xa8\xaf&\xcbNu8,\x99\x94\xda\x17\x9a\x93\xeaZ\xd4\xd3\x85r\xedO8\xf6\xa8\xef\x0b\xdc\xf7jO\x82\xdf_\xe0\x9eB}\\j\xbc~u\x9f\xba\xa2\xe0t@\x9dh\xd1G\x13\xea\x81\x02oy\xf8\xf6\x87V\x13\x8f3u\x14h\x07>\x01;\xe2\\w\x02\xab\x80w\xc0d|O\xe1\n0\x03X\n<\x03.\x03_\x80\xab\xc0\x02`\x14uJ\xfd\xa1n/m}~4\xe5x\x8b\x9d\x941\x1e\xdc\xf9%\x8dm\xa1=E\\Ve\x11\x98\x8f\x95:\xdcN\xf8\xf7\xa9\x93\r\xe0%p>q,C5\xc7V\xc79\x07\xbcl\x90\x8f\xfbe\t\xe2\xe0?\x04Jq\x96\x01c\r`\x98\xfc\xcd\xa9\xc2S\xe0cb\xfd#\xf0$\xb1\xde\x05\x0c7\x80K@\xaf\x9aU\x10?\x87M\x00\xe3%\x9b\x88\xb5\xd1V\x8e\xa1\xd9\x0b\\j\x00w\xc8\x87\xe4\x86\x8a@\x87\x81\x17\xe4\xe5\xde\xca\x9e\x03U\xb3o\x03y\xd9\xdfiF\xeeU\x1f\xaa\x9b\xd4\x95\xea\x9c\xf8\xde\xa3\xbeP\x17U\x085\x87\xe7suk\xfc\x9e\x13\x1a\x9b\xd4\x07jo\xd9\xe1|\x94\xeawuD\xbd\xab\xbeU\xd7W\x05)\xf8\xaeU\xdf\x84\xcfHh\xa8\xfe]\xcdj\x9b:P\xea\x8f\x9fj\xddT@]\xe7\x9f\xc1\xdc\xc4\x80\xdaV\xe5\xb0(\xb2*b\xc4\xc4;e\xfe|\xdf/\xf9\xdcM\x1dwqgg\xccGS\x13g\x13\xfc\xbd\x05\xdeT\xf8\xb6\xdeI\x85@\xb7z\xd3|V\xa9\xeeQ\x17\xaa\xb3\xc3:\xe2n>\x04\xe7\xa6\xda]\xa5W\xd5;\xcd`\x19y\xc3\xed\x04\xd6\x00\xb3\x80\xe6\x9f\xc4\x06\xf0\rxD\xde\x8bCY\x96Y\xa5\xf5\x0b\xb9s\x8e\xb9\xf4\x11\x12=\x00\x00\x00\x00IEND\xaeB`\x82'
    mark_goal = Image.open(BytesIO(mark_goal_bytes))
    mark_assist_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x1a\x00\x00\x00\x1a\x08\x06\x00\x00\x00\xa9JL\xce\x00\x00\x01\xe7IDATx\x9c\xed\xd4\xcb\x8b\x8fQ\x1c\x06\xf0\xe7\xb0b\xe3\x92r\xdd(%\xa3H\x88\xc6b\xa4\\R\x8ab\xc5\xccB\x94\x92\xd8H\xa9\xf9\x03\x14\x91"\x89\x95\xcbF.\x1b+\xd4\x94\xdbF\xb9m\xa4,0\x98\xa1\x8c0\xc5h|,~\xef\xe4g2ch\xb2\x9a\xa7\xde\xc5\xf7|\xcf9\xcf\xfb<\xe79\'\x19\xc1\x08\xfe;0\xef\x0f\xfd\x05\x982\x1cD\x9f\xd1\xf2\x9b\xf1i8\x8c\x1e\xbc\xc1)\xac\xf8W\x9e\x02I\xbe\'\xb9\x92\xe4Z\x92\xde$\x8b\x93\xacKR\xaf\xa4\'\xc9\xd6$\xdf\x92\xccNr\xa0\x94\xd2\xf37\x8a\x86\x82\xc7X\x8aV|\xc1>\xac\xc5\x19l\xc4\xb8\xa1\x10m\xc3Yt\x0c@r\x01sq\t\x9dX\x85\xed\xe8\xae\x9b\xf3\x12\xc7\xd00\x10\xcf\xa8$MI\xae\'\xd9\x90dg\x92G}\xff\x90\xa45\xc9\xc1$\x97*\x1bWV\x96\x9eL2\xb6n\x9f\xae$\xcf\x93\x8c\xc7\x1a4c\xfa@\xd6u\xe0He\xd1nlF\x0b>\xe28\xe6\xa3\xad\x9f\xda\xf7\xd8\x81F\x1c\xc5\x8b\xba\xde;\x9cG\xd3@g\xd4\x85\xbd\x98\x80\xdb\xd8\x85\xd5h\xef7\xef)\x96`?>\xfd\xdeu\xf0\x15\xcd\x83\x85\xe1*&a\x0b\xbe\xf5\xeb\xbd\xc6B\xb50\x0c\x05\xed\x7fJ\xdde,W\xbbk}\xf8\x8eM84D\x120*\xc9\x93AB\xb9>\xc9\xac$\xa7\xeb\xc6n$\xf9\x90d\xcf \xeb\xfa\xe3~\xb0\x0c\x0f\xfc\xb4\xa7G-\xc6\xbdU}\x17Mj\xafCG\xa5\xe6\\\x9d\xba\xb7jwK\xb5\xa6\xb3\xda\x83\xda\xf9\\\xc5\x9c\xbe@\x8cQ\xbb\x94pS\xed\xf9yU\xd5W0\x1a\x13\xabo4NT\xbdO\x98\x89\x8bU\xdd\x8e\xa9\xb8U\xd5\x0f\xfb$\x95\xba\x98/J29I{)\xe5!\x1a\x93LH\xf2\xac\x94\xf2\x8b\xbd\x98\x99\xa4!Iw)\xa5\r\xb3+\x8b\xbbJ)w0?\xc9\x8c$\x9d\xa5\x94{\x7fa\xf1\x08F0\x8c\xf8\x01\x19u,\x90\x1b\xe7-\xc4\x00\x00\x00\x00IEND\xaeB`\x82'
    mark_assist = Image.open(BytesIO(mark_assist_bytes))

    ga_font = font_ds.get_font(font).font_variant(size=28)
    player_font = font_ds.get_font(font).font_variant(size=21)
    picture = Image.new('RGBA', (190, 235), (0, 0, 0, 0))
    draw = ImageDraw.Draw(picture)

    x_offset = (goals+assists > 0) * 17
    draw.rectangle([(x_offset+18, 0), (x_offset+173, 155)], fill='white')
    player_picture = player_ds.get_picture(player).resize((145, 145))
    picture.paste(player_picture, (x_offset+18+5, 5))

    y_offset = (goals*assists > 0) * 70
    if goals:
        draw.rectangle([(0, 0), (30, 60)], fill='#620931')
        picture.paste(mark_goal, (2, 2), mark_goal)
        draw.text((15 - ga_font.getlength(str(goals))//2, 30), str(goals), font=ga_font, fill='white')
    if assists:
        draw.rectangle([(0, y_offset), (30, y_offset+60)], fill='#620931')
        picture.paste(mark_assist, (2, y_offset+2), mark_assist)
        draw.text((15 - ga_font.getlength(str(assists))//2, y_offset+30), str(assists), font=ga_font, fill='white')

    # draw.rectangle([(0, 160), (190, 210)], fill='white')
    player_fn = player.split()
    draw.text(
        (95 - player_font.getlength(player_fn[0])//2, 160+2 + 0*24),
        player_fn[0],
        font=player_font,
        fill='white')
    draw.text(
        (95 - player_font.getlength(player_fn[1])//2, 160+2 + 1*24),
        player_fn[1],
        font=player_font,
        fill='white')

    if text:
        text_font_size = min(int(16*23/team_len(text)), 22)
        text_font = font_ds.get_font(font).font_variant(size=text_font_size)
        text_width = min(text_font.getlength(text), 190)
        # second_name_width = min(player_font.getlength(player_fn[1]), 190)
        # text_rectangle_width = max(text_width, second_name_width)
        # draw.rectangle([(max(85 - text_rectangle_width//2, 0), 210), (min(105 + text_rectangle_width//2, 190), 235)], fill='white')
        draw.text(
            (95 - text_width//2, 208 + (27-text_font_size)//2),
            text,
            font=text_font,
            fill='white')

    return picture


def make_line_picture(players_count, players_pictures):
    # Создание картинки линии игроков (вратарь/защита/полузащита/нападение)
    if players_count > 3:
        picture = Image.new('RGBA', (385, 720), (0, 0, 0, 0))
    else:
        picture = Image.new('RGBA', (190, 720), (0, 0, 0, 0))

    if players_count == 5:
        picture.paste(make_line_picture(2, (players_pictures[1], players_pictures[3])), (0, 0))
        picture.paste(make_line_picture(3, (players_pictures[0], players_pictures[2], players_pictures[4])), (195, 0))
    elif players_count == 4:
        picture.paste(make_line_picture(2, (players_pictures[1], players_pictures[2])), (0, 0))
        picture.paste(make_line_picture(-2, (players_pictures[0], players_pictures[3])), (195, 0))
    elif players_count == 3:
        picture.paste(players_pictures[0], (0, 3))
        picture.paste(players_pictures[1], (0, 243))
        picture.paste(players_pictures[2], (0, 483))
    elif players_count == 2:
        picture.paste(players_pictures[0], (0, 83))
        picture.paste(players_pictures[1], (0, 403))
    elif players_count == -2:
        picture.paste(players_pictures[0], (0, 3))
        picture.paste(players_pictures[1], (0, 483))
    elif players_count == 1:
        picture.paste(players_pictures[0], (0, 243))

    return picture


def make_team_picture(background_ds, font_ds, font, player_ds, players, title, tournament):
    # Создание окончательной картинки с командой
    picture = background_ds.get_picture('horizontal').resize((1280, 960))
    big_font = font_ds.get_font(font).font_variant(size=60)
    small_font = font_ds.get_font(font).font_variant(size=30)
    caption_font = font_ds.get_font(font).font_variant(size=20)

    draw = ImageDraw.Draw(picture)
    draw.text((50, 40), title[0], font=big_font, fill='white')
    draw.text((50, 110), title[1], font=small_font, fill='white')
    draw.text((50, 910), tournament_to_caption(tournament), font=caption_font, fill='white')

    offset = 50
    line_players_count = tuple(map(len, players))
    wide_line_count = len(tuple(filter(lambda x: x>3, line_players_count)))
    line_offset = (420 - wide_line_count*195) // 3
    for line, players_count in zip(players, line_players_count):
        players_pictures = []
        for player in line:
            pl, text, goals, assists, position = player
            player_picture = make_player_picture(font_ds, font, player_ds, pl, text, goals, assists)
            players_pictures.append(player_picture)
        line_picture = make_line_picture(players_count, players_pictures)
        picture.paste(line_picture, (offset, 172), line_picture)
        offset += 190 + (players_count > 3)*195 + line_offset

    return picture


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
    def __init__(self, alternative=None):
        pass

    def get_timetable(self, key):
        print('Из этого источника данных невозможно получить расписание')

    def get_picture(self, key):
        print('Из этого источника данных невозможно получить картинку')

    def get_tournament_table(self, key):
        print('Из этого источника данных невозможно получить турнирную таблицу')

    def get_shortname(self, key):
        print('Из этого источника данных невозможно получить сокращённое название команды')

    def get_font(self, key):
        print('Из этого источника данных невозможно получить шрифт')

    def get_tournament_code(self, key):
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

    def get_font(self, key):
        if key not in self.__cache:
            self.__cache[key] = self.__ds.get_font(key)
        return self.__cache[key]


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
    # Класс для получения кода турнирна из источника данных
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

    def get_font(self, key):

        worksheet = self.__ds
        font = None
        try:
            cell = worksheet.find(key.strip().lower())
            url = worksheet.cell(cell.row, cell.col+1).value
            buf = BytesIO(download_file(url))
            font = ImageFont.FreeTypeFont(buf)
        except:
            if self.__alternative:
                alternative_ds = GetFont(GoogleColabInput())
                font = alternative_ds.get_font(key)
        return font

    def get_tournament_code(self, tournament):

        worksheet = self.__ds
        tournament_codes = None
        try:
            criteria_re = re.compile(tournament.strip().lower())
            cell_list = worksheet.findall(criteria_re)
            if not cell_list:
                raise Exception()
            tournament_codes = []
            for cell in cell_list:
                tournament_codes.append(worksheet.cell(cell.row, cell.col+1).value)
        except:
            if self.__alternative:
                alternative_ds = GetTournamentCode(GoogleColabInput())
                tournament_codes = alternative_ds.get_tournament_code(tournament)
        return tournament_codes


class GoogleColabInput(DataSource):
    # Класс для источника данных - ввод в google colab
    def get_picture(self, key=''):
        if key == '':
            print(f'↓ Загрузи картинку')
        else:
            print(f'↓ Загрузи картинку "{key}" вручную, т.к. её нет в базе данных')
        picture = files.upload()
        buf = BytesIO(picture[list(picture.keys())[0]])
        return Image.open(buf)

    def get_font(self, key=''):
        if key == '':
            print(f'↓ Загрузи шрифт')
        else:
            print(f'↓ Загрузи шрифт "{key}" вручную, т.к. его нет в базе данных')
        font = files.upload()
        buf = BytesIO(font[list(font.keys())[0]])
        return ImageFont.FreeTypeFont(buf)

    def get_shortname(self, team):
        return input(f'Введите сокращенное название для команды "{team}"\n')

    def get_tournament_code(self, tournament):
        print(f'Водите коды для каждого турнира "{tournament}" с новой строки\n')
        tournament_codes = []
        s = input()
        while s:
            tournament_codes.append(s)
            s = input()
        return tournament_codes


class FootballMSUSiteOld(DataSource):
    # Класс для источника данных - http://football.msu.ru
    __alternative = False

    def __init__(self, alternative=False):
        self.__alternative = alternative

    def get_tournament_table(self, code):
        tournament_table = None
        try:
            url = f'http://football.msu.ru/tournament/{code.split()[0]}/tables?round_id={code.split()[1]}'
            soup = BeautifulSoup(requests.get(url).text, 'lxml')
            tournament = soup.find('div', {'class': "tournaments-tables-title left mobile-hide"}).text.strip()
            table = soup.find('div', {'id': "tournamentTablesTable",
                              'class': "tournaments-tables-cont sfl-tab-cont mobile"}).find('table')
            rows = table.find_all('tr')
            columns = list(map(lambda x: x.text.strip(), rows[0].find_all('th')))[1:-1]
            teams = [list(map(lambda x: x.text.strip(), r.find_all('td')))[2:-1] for r in rows[1:]]
            tournament_table = pd.DataFrame(teams, columns=columns)
            tournament_table.index.name = tournament
        except:
            if self.__alternative:
                pass
        return tournament_table

class FootballMSUSite(DataSource):
    # Класс для источника данных - http://footballmsu.ru
    __alternative = False

    def __init__(self, alternative=False):
        self.__alternative = alternative

    def get_tournament_table(self, code):
        tournament_table = None
        try:
            url = f'http://footballmsu.ru/tournament/{code.split()[0]}/tables?round_id={code.split()[1]}'
            soup = BeautifulSoup(requests.get(url).text, 'lxml')
            tournament = soup.find('div', {'class': "tournaments-tables-title left mobile-hide"}).text.strip()
            table = soup.find('div', {'id': "tournamentTablesTable",
                              'class': "tournaments-tables-cont sfl-tab-cont mobile"}).find('table')
            rows = table.find_all('tr')
            columns = list(map(lambda x: x.text.strip(), rows[0].find_all('th')))[1:-1]
            teams = [list(map(lambda x: x.text.strip(), r.find_all('td')))[2:-1] for r in rows[1:]]
            tournament_table = pd.DataFrame(teams, columns=columns)
            tournament_table.index.name = tournament
        except:
            if self.__alternative:
                pass
        return tournament_table
