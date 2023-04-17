import math
from typing import List
from lark import Lark, Transformer


class SimaiTransformer(Transformer):
    def title(self, n):
        n = n[0]
        return {"type": "title", "value": n.rstrip()}

    def artist(self, n):
        n = n[0]
        return {"type": "artist", "value": n.rstrip()}

    def smsg(self, n):
        pass

    def des(self, n):
        if len(n) == 1:
            n = n[0]
            return {"type": "des", "value": n.rstrip()}
        elif len(n) == 2:
            num, des = n
            return {"type": "des", "value": (int(num), des.rstrip())}

    def freemsg(self, n):
        pass

    def first(self, n):
        if len(n) == 1:
            n = n[0]
            return {"type": "first", "value": n.rstrip()}
        elif len(n) == 2:
            num, first = n
            return {"type": "first", "value": (int(num), first)}

    def pvstart(self, n):
        pass

    def pvend(self, n):
        pass

    def wholebpm(self, n):
        n = n[0]
        return {"type": "wholebpm", "value": n.rstrip()}

    def level(self, n):
        num, level = n
        return {"type": "level", "value": (int(num), level.rstrip())}

    def chart(self, n):
        num, raw_chart = n
        chart = ""
        for x in raw_chart.splitlines():
            if "||" not in x:
                chart += x

        chart = "".join(chart.split())
        return {"type": "chart", "value": (int(num), chart)}

    def amsg_first(self, n):
        pass

    def amsg_time(self, n):
        pass

    def amsg_content(self, n):
        pass

    def demo_seek(self, n):
        pass

    def demo_len(self, n):
        pass

    def chain(self, values):
        result = []
        for value in values:
            if isinstance(value, dict):
                result.append(value)

        return result


class FragmentTransformer(Transformer):
    def bpm(self, n) -> dict:
        (n,) = n
        event_dict = {
            "type": "bpm",
            "value": float(n),
        }
        return event_dict

    def divisor(self, n) -> dict:
        (n,) = n
        if float(n) == 0:
            raise ValueError("Divisor is 0.")

        event_dict = {
            "type": "divisor",
            "value": float(n),
        }
        return event_dict

    def equivalent_bpm(self, n) -> dict:
        if len(n) == 0:
            return {"type": "equivalent_bpm", "value": None}

        (n,) = n
        return {"type": "equivalent_bpm", "value": float(n)}

    def duration(self, items) -> dict:
        # Set defaults
        equivalent_bpm = None
        den = None
        num = None

        for item in items:
            if isinstance(item, str) and item.type == "INT" and den is None:
                den = int(item)
                if den <= 0:
                    return {
                        "type": "duration",
                        "equivalent_bpm": equivalent_bpm,
                        "duration": 0,
                    }
            elif isinstance(item, str) and item.type == "INT" and num is None:
                num = int(item)
            elif isinstance(item, str) and item[-1] == "#":
                equivalent_bpm = float(item[:-1])

        if den is None or num is None:
            raise ValueError("No denominator or numerator given")

        return {
            "type": "duration",
            "equivalent_bpm": equivalent_bpm,
            "duration": num / den,
        }

    def slide_pos(self, items) -> dict:
        return {
            "type": "slide_pos",
            "pos": items[0].value
        }

    def slide_connector(self, items) -> dict:
        connector_str = items[0].value
        if connector_str.startswith("V"):
            return {
                "type": "slide_connector",
                "pattern": "V",
                "reflect": int(connector_str[1]) - 1
            }

        return {
            "type": "slide_connector",
            "pattern": connector_str
        }

    def slide_modifier(self, items) -> dict:
        return {
            "type": "slide_modifier",
            "modifier": items[0].value
        }

    def slide_beg(self, items) -> dict:
        slides = []
        current_slide = None
        slide_modifier = ""

        for i in items:
            if i['type'] == "slide_connector":
                if current_slide is not None:
                    slides.append(current_slide)
                current_slide = {
                    "type": "connected_slide" if current_slide is not None else "slide",
                    "start": current_slide['end'] if current_slide is not None else None,
                    "pattern": i['pattern'],
                    "reflect": i['reflect'] if 'reflect' in i else None,
                    "end": None,
                    "duration": None,
                    "equivalent_bpm": None
                }

            if i['type'] == "slide_pos":
                current_slide["end"] = i["pos"]

            if i['type'] == "duration":
                current_slide["duration"] = i["duration"]
                current_slide["equivalent_bpm"] = i['equivalent_bpm']

            if i['type'] == "slide_modifier":
                slide_modifier += i["modifier"]

        slides.append(current_slide)

        return {
            "type": "slide_beg",
            "slides": slides,
            "slide_modifier": slide_modifier
        }

    def chained_slide_note(self, item) -> dict:
        slides = []
        slide_modifier = ""
        for i in item:
            if 'type' in i and i['type'] == 'slide_beg':
                slides = i['slides']
                slide_modifier = i['slide_modifier']

        return {
            "type": "chained_slide_note",
            "slides": slides,
            "slide_modifier": slide_modifier
        }

    def slide_note(self, items) -> dict:
        slides = []
        slide_modifier = []
        star_modifier = ""
        slide_pos = None
        for i in items:
            if i['type'] == "slide_pos":
                slide_pos = i['pos']
            if i['type'] == 'slide_modifier':
                star_modifier = i['modifier']
            if i['type'] == 'slide_beg':
                slides.append(i['slides'])
                slide_modifier.append(i['slide_modifier'])
            if i['type'] == 'chained_slide_note':
                slides.append(i['slides'])
                slide_modifier.append(i['slide_modifier'])

        for i in slides:
            i[0]['start'] = slide_pos
            only_last_slide_has_duration = i[-1]['duration'] is not None
            all_slide_has_duration = i[-1]['duration'] is not None
            for j in i[:-1]:
                if j['duration'] is None:
                    all_slide_has_duration = False
                else:
                    only_last_slide_has_duration = False

            if not only_last_slide_has_duration and not all_slide_has_duration:
                raise ValueError(
                    "Please only specify duration in last slide or specify all slide duration in the combined slide.")

            if only_last_slide_has_duration and len(i) != 1:
                # Connect slide need to strictly follow last note's resolution
                # 1 off error will cause all notes afterward disappear or even game crashes
                # Here will round all average note's duration by resolution to prevent error
                resolution = 384
                equivalent_bpm = i[-1]['equivalent_bpm']
                duration_by_resolution = round(i[-1]['duration'] * resolution)
                last_note_duration_by_resolution = duration_by_resolution
                average_duration_by_resolution = math.floor(duration_by_resolution / len(i))
                # the tick lost is to compensate the tick lose because of using floor on average duration
                # to prevent the duration of last notes off too much with others
                tick_lost = duration_by_resolution / len(i) - average_duration_by_resolution
                total_missed_ticks = 0
                for j in i[:-1]:
                    j['duration'] = average_duration_by_resolution
                    j['equivalent_bpm'] = equivalent_bpm
                    last_note_duration_by_resolution -= average_duration_by_resolution
                    total_missed_ticks += tick_lost
                    if total_missed_ticks >= 1:
                        j['duration'] += 1
                        total_missed_ticks -= 1
                        last_note_duration_by_resolution -= 1
                i[-1]['equivalent_bpm'] = equivalent_bpm
                i[-1]['duration'] = last_note_duration_by_resolution

                for j in i:
                    j['duration'] = j['duration'] / resolution

        return {
            "type": "slide_fes",
            "modifier": star_modifier,
            "slide_modifier": slide_modifier,
            "slides": slides,
            "start_button": slide_pos
        }

    def tap_hold_note(self, items):
        if len(items) == 2:
            (
                text,
                duration_dict,
            ) = items
        else:
            (text,) = items
            duration_dict = None

        button = int(text[0]) - 1
        text = text[1:]
        if button == -1:
            # Ignore simai notes that has button position 0
            return

        is_tap = True
        if "h" in text:
            is_tap = False

        modifier = ""
        for char in text:
            if char == "h":
                continue

            if char in "bx":
                modifier += char

            if is_tap and char in "$":
                modifier += char

        if not is_tap:
            if duration_dict is None:
                duration = 0
            else:
                duration = duration_dict["duration"]

            return {
                "type": "hold",
                "button": button,
                "modifier": modifier,
                "duration": duration,
            }

        return {
            "type": "tap",
            "button": button,
            "modifier": modifier,
        }

    def touch_tap_hold_note(self, items):
        if len(items) == 2:
            (
                text,
                duration_dict,
            ) = items
        else:
            (text,) = items
            duration_dict = None

        region = text[0]
        if len(text) > 1 and text[1] in "012345678":
            position = int(text[1]) - 1
            text = text[2:]
        else:
            position = 0
            text = text[1:]

        if region not in "ADCBE" or position == -1:
            return

        is_tap = True
        if "h" in text:
            is_tap = False

        modifier = ""
        for char in text:
            if char == "h":
                continue

            if char in "f":
                modifier += char

        if not is_tap:
            if duration_dict is None:
                duration = 0
            else:
                duration = duration_dict["duration"]

            return {
                "type": "touch_hold",
                "region": region,
                "location": position,
                "modifier": modifier,
                "duration": duration,
            }

        return {
            "type": "touch_tap",
            "region": region,
            "location": position,
            "modifier": modifier,
        }

    def pseudo_each(self, items):
        (item,) = items
        if isinstance(item, list):
            notes = item
        elif isinstance(item, dict):
            notes = [item]
        else:
            raise TypeError(f"Invalid type: {type(item)}")

        for note in notes:
            note["modifier"] += "`"

        return notes

    def chain(self, items) -> list:
        result = []
        # Flatten list
        for item in items:
            if isinstance(item, list):
                for subitem in item:
                    result.append(subitem)
            elif isinstance(item, dict):
                result.append(item)
        return result


def process_chained_slides(
        start_button: int,
        duration: dict,
        equivalent_bpm: dict,
        slide_modifier: str,
        chained_slides: List[dict],
):
    complete_slides = []
    for slide in chained_slides:
        if start_button == -1 or slide["reflect"] == -1 or slide["end"] == -1:
            continue

        duration = duration if slide["duration"] is None else slide["duration"]
        equivalent_bpm = (
            equivalent_bpm
            if slide["equivalent_bpm"] is None
            else slide["equivalent_bpm"]
        )

        note_dict = {
            "type": "slide",
            "start_button": start_button,
            "modifier": slide_modifier,
            "pattern": slide["pattern"],
            "reflect_position": slide["reflect"],
            "end_button": slide["end"],
            "duration": duration,
            "equivalent_bpm": equivalent_bpm,
        }
        complete_slides.append(note_dict)

    return complete_slides


def parse_fragment(fragment: str, lark_file: str = "simai_fragment.lark") -> List[dict]:
    parser = Lark.open(lark_file, rel_to=__file__, parser="earley")
    try:
        return FragmentTransformer().transform(parser.parse(fragment))
    except Exception:
        print(f"Error parsing {fragment}")
        raise
