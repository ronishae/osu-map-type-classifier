import csv
import logging
import numpy as np
import math
from dataclasses import dataclass
OUTPUT_FILE_HEADER = "HPDrainRate,CircleSize,OverallDifficulty,ApproachRate,SliderMultiplier,SliderTickRate\n"

@dataclass 
class HitObject():
    x: int = None
    y: int = None
    time: int = None

@dataclass
class HitCircle(HitObject):
    pass

@dataclass
class Slider(HitObject):
    sliderType: str = None
    # lastTime: int
    lastX: int = None
    lastY: int = None
    numSlides: int = None
    sliderLength: float = None
    timeLength: float = None
    totalSliderLength: float = None

@dataclass
class Spinner(HitObject):
    endTime: float = None


@dataclass
class MapInfo():
    """
    xs: a list of x positions of the hit objects.
    ys: a list of y positions of the hit objects.
    times: a list of times hit objects appear.
    x_diffs: a list of differences in x between consecutive objects in the map.
    y_diffs: a list of differences in y between consecutive objects in the map.
    dists: a list of distances between consecutive objects in the map.
    time_diffs: a list of differences in time (milliseconds) between consecutive objects in the map.
    num_circles: the number of hit circle objects in the map.
    num_sliders: the number of slider objects in the map.
    num_spinners: the number of spinner objects in the map.
    hit_objects: a list of HitCircle, Slider, and Spinner objects.
    slider_counts: a dictionary holding the amount of occurrences of each slider type
    B (Bezier) type sliders
    C (Centripetal catmull-rom) type sliders
    L (Linear) type sliders
    P (Perfect Circle) type sliders
    length: the time between the first and last hit object
    """
    xs: list[float]
    ys: list[float]
    times: list[int]
    x_diffs: list[float]
    y_diffs: list[float]
    dists: list[float]
    time_diffs: list[int]
    num_circles: int
    num_sliders: int
    num_spinners: int
    hit_objects: list[HitCircle|Slider|Spinner]
    slider_counts: dict[str:int]
    length: int

@dataclass
class ComputedInfo():
    """
    avgDist: the average distance between two objects in pixels (spinner excluded)
    avgTime: the average % of beat length between two objects. Ignores time difference if the difference is over 800ms
    (this number is somewhat arbtrirary, but it is to ensure breaks are ignored)
    The rest of the attributes are the percent of hit objects (includes spinner) mapped at that time
    """
    avgDist: float
    avgTime: float
    wholes: float
    halves: float
    thirds: float
    fourths: float
    sixths: float
    eigths: float
    twelfths: float
    sixteenths: float


def _seek_to_section(in_file, section) -> None:
    """Jumps to the given section in the file (case sensitive).

    The next line read after this function will be the first line
    of that section.

    in_file -- the opened file to read
    section -- the name of the section
    """
    row = in_file.readline()
    while (f"[{section}]") not in row:
        row = in_file.readline()

    return

def _read_difficulty(in_file) -> str:
    """Outputs a comma seperated string with the difficulty parameters.

    Assumes the file is in v14.osu format,
    and has not read past the difficulty section.
    
    in_file -- the opened file to read
    """
    logging.debug("Reading difficulty information.")
    _seek_to_section(in_file, "Difficulty")

    line = ""
    NUM_DIFFICULTY_ELEMENTS = 6
    for i in range(NUM_DIFFICULTY_ELEMENTS):
        row = in_file.readline()
        line += row.split(':')[1]
        if i != NUM_DIFFICULTY_ELEMENTS - 1:
            line += ','

    line = line.replace('\n', '') # remove the line breaks in between
    return line

def _get_beat_lengths(in_file) -> list[tuple[int, float]]:
    """Returns a list of time-length pairs.

    The first element is the time in milliseconds.
    The second element is the beat-length.

    Assumes the file is in v14.osu format,
    and has not read past the difficulty section.

    in_file -- the file to read
    """
    logging.debug("Reading beat length information.")
    _seek_to_section(in_file, "TimingPoints")
    beat_lengths = []

    row = in_file.readline()
    while row != '\n' and '[' not in row and ']' not in row:
        parsed = row.split(',')
        time = int(parsed[0])
        beat_length = float(parsed[1])

        # if beat_length >= 0: # only want non-inherited beat lengths
        pair = (time, beat_length)
        beat_lengths.append(pair)
            
        row = in_file.readline()
    
    return beat_lengths

def _get_latest_beat_length(times: list[tuple[int, float]], time: int) -> tuple[float, float]:
    """The second value is the beat length corresponding to the largest time in the list 
    which is less than the given time. Assumes the times list is sorted. 
    Assumes non-empty list. The first value is the most recent non-negative beat length before
    the second value."""
    pos = times[0]
    cur = times[0]
    for candidate in times:
        if candidate[1] > 0:
            pos = candidate

        if candidate[0] < time:
            cur = candidate

    return (pos[1], cur[1])


def _is_circle(num) -> bool:
    """The type is a circle if and only if the first bit is set."""
    return num & 1

def _is_slider(num) -> bool:
    """The type is a slider if and only if the second bit is set."""
    return num & 1 << 1

def _get_object_type(num) -> str:
    """Outputs the name of the object type"""
    if _is_circle(num):
        return "circle"
    elif _is_slider(num):
        return "slider"
    else:
        return "spinner"

def _compute_slider_time_length(totalLength: float, prevBeatLength: float, 
                                latestBeatLength: float, sliderMult: float) -> float:
    """Calculates the length of time a slider exists for.
    TODO: do some tests
    """
    if latestBeatLength >= 0:
        beatLength = latestBeatLength
    else:
        beatLength = prevBeatLength * abs(latestBeatLength) / 100

    return totalLength * beatLength / (sliderMult * 100)

def _parse_slider(parsed_cur: list[str], slider_counts: dict[str:int], beat_lengths: list[tuple[int, float]], sliderMult: float) -> Slider:
    """Returns a Slider object with initiated attributes (except for x, y, time).
    Also updates the given dictionary's slider counts based on the slider type."""
    slider = Slider()

    params = parsed_cur[5].split('|')
    slider_type = params[0]
    slider_counts[slider_type] += 1
    first_point = params[1].split(':')
    first_x = int(first_point[0])
    first_y = int(first_point[1])

    last_point = params[-1].split(':')
    last_x = int(last_point[0])
    last_y = int(last_point[1])
    numSlides = int(parsed_cur[6])
    sliderLength = float(parsed_cur[7])

    # even number of slides means it ends on the starting point
    if numSlides % 2 == 1:
        slider.lastX = last_x
        slider.lastY = last_y
    else:
        slider.lastX = first_x
        slider.lastY = first_y

    slider.sliderType = slider_type
    slider.numSlides = numSlides
    
    slider.sliderLength = sliderLength
    slider.totalSliderLength = numSlides * sliderLength
    time = int(parsed_cur[2])
    ret = _get_latest_beat_length(beat_lengths, time)
    slider.timeLength = _compute_slider_time_length(slider.totalSliderLength, ret[0], 
                                                    ret[1], sliderMult)

    return slider

def _get_info(in_file, beatLengths: list[tuple[int, float]], sliderMult: float) -> MapInfo:
    """Returns a list information on the hit objects in the map.

    Differences are calculated from the later object to the earlier object.
    Assumes non-empty hit object list.
    """
    logging.info("Started reading hit object information.")
    hit_objects = []
    num_sliders, num_circles, num_spinners = 0, 0, 0
    slider_counts = {'B': 0, 'C': 0, 'L': 0, 'P': 0}

    _seek_to_section(in_file, "HitObjects")

    # read from file into memory
    x_list = []
    y_list = []
    time_list = []
    cur = in_file.readline()
    start = int(cur.split(',')[2])

    while cur != '':
        parsed_cur = cur.split(',')
        new_hitObject = HitObject()

        # update object counts
        obj_type = int(parsed_cur[3])
        if _is_slider(obj_type):
            num_sliders += 1
            new_hitObject = _parse_slider(parsed_cur, slider_counts, beatLengths, sliderMult)
            
        elif _is_circle(obj_type): 
            num_circles += 1
            new_hitObject = HitCircle()
        else: # spinner
            num_spinners += 1
            new_hitObject = Spinner()
            new_hitObject.endTime = int(parsed_cur[5])

        # read hit object information
        x = int(parsed_cur[0])
        y = int(parsed_cur[1])
        time = int(parsed_cur[2])

        x_list.append(x)
        new_hitObject.x = x
        
        y_list.append(y)
        new_hitObject.y = y

        time_list.append(time)
        new_hitObject.time = time

        hit_objects.append(new_hitObject)

        end = int(cur.split(',')[2])
        cur = in_file.readline()
    
    length = end - start

    # short computations
    objects = np.array([x_list, y_list, time_list])
    x_diff, y_diff, time_diff = np.diff(objects, axis=1)
    distances = np.sqrt(x_diff ** 2 + y_diff ** 2)

    outInfo = MapInfo(x_list, y_list, time_list, x_diff, y_diff, distances, 
                      time_diff, num_circles, num_sliders, num_spinners,
                      hit_objects, slider_counts, length)
    logging.info("Finished reading hit object information.")
    return outInfo

def _compute_attributes(info: MapInfo, beat_lengths: list[tuple[int, float]]) -> ComputedInfo:
    """
    Does more "advanced" computation using the map info
    """
    logging.info("Started computing attributes.")
    formatted_output = ''

    logging.info("Finished computing attributes.")
    return formatted_output
    

def parse_osu(input_file_name):
    """Parses the osu formatted file and outputs it as a csv file."""
    logging.info(f"Started parsing file {input_file_name}.")
    # TODO apparently using with is better so change it
    in_file = open(input_file_name, encoding="utf8", mode='r')
    out = open("output.csv", 'w')

    out.write(OUTPUT_FILE_HEADER)

    # first line is always version declaration
    version = in_file.readline()

    line = ''
    # read in difficulty
    difficulty = _read_difficulty(in_file)
    line += difficulty
    sliderMult = float(difficulty.split(',')[4])
    
    # get list of beat lengths
    beat_lengths = _get_beat_lengths(in_file)

    info = _get_info(in_file, beat_lengths, sliderMult)
    _show_info_debug(info)

    computed = _compute_attributes(info, beat_lengths)

    line += '\n'
    out.write(line)

    out.close()
    in_file.close()
    logging.info(f"Finished parsing file {input_file_name}.")
    return

def _show_info_debug(info: MapInfo) -> None:
    for obj in info.hit_objects:
        print(obj)
        print("\n")

    print(info.slider_counts)

if __name__ == "__main__":
    logging.basicConfig(filename='parser.log',filemode='w', level=logging.INFO, 
                        format='%(asctime)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')

    input_file = "quaver.osu" 
    parse_osu(input_file)

