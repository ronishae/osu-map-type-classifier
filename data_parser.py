import csv
import logging
import numpy as np
import math
import os
from dataclasses import dataclass
from collections import OrderedDict
MAP_DIRECTORY = 'map_data/'
OUTPUT_FILE_HEADER = "HPDrainRate,CircleSize,OverallDifficulty,ApproachRate,SliderMultiplier,avgDist,avgTime,wholes,halves,thirds,fourths,sixths,eigths,twelfths,sixteenths,other,target\n"
TIMING_TOLERANCE = 0.05
FRACTIONS = {
    'wholes': 1,
    'halves': 1/2,
    'thirds': 1/3,
    'fourths': 1/4,
    'sixths': 1/6,
    'eigths': 1/8,
    'twelfths': 1/12,
    'sixteenths': 1/16
}

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
    lastX: int = None
    lastY: int = None
    lastPoint: tuple[int, int] = None
    numSlides: int = None
    sliderLength: float = None
    timeLength: float = None
    totalSliderLength: float = None
    endTime: float = None

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
    avgDist: the average distance between two objects in pixels
    avgTime: the average % of beat length between two objects. Ignores time difference if the difference is over 2 seconds
    (this number is somewhat arbtrirary, but it is to ensure breaks are ignored)
    timingDict: count of each timing
    timingPercents: a dictionary storing the percentage of notes mapped at a specific timing interval.
    Possible options include: wholes, halves, thirds, fourths, sixths, eigths, twelfths, sixteenths. Total
    may not sum to 1 due to missing timing intervals or some excluded notes or rounding.
    """
    avgDist: float
    avgTime: float
    timingDict: dict[str:int]
    timingPercents: dict[str:float]

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

def _get_current_beat_length(timingPoints: list[tuple[int, float]], time: int) -> float:
    prevBeatLength, latestBeatLength = _get_latest_beat_length(timingPoints, time)
    if latestBeatLength >= 0:
        beatLength = latestBeatLength
    else:
        beatLength = prevBeatLength * abs(latestBeatLength) / 100

    return beatLength

def _get_latest_beat_length(timingPoints: list[tuple[int, float]], time: int) -> tuple[float, float]:
    """The second value is the beat length corresponding to the largest time in the list 
    which is less than the given time. Assumes the timingPoints list is sorted. 
    Assumes non-empty list. The first value is the most recent non-negative beat length before
    the second value."""
    pos = timingPoints[0]
    cur = timingPoints[0]
    for candidate in timingPoints: # candidate is of form (time, beatLength)
        if candidate[1] > 0:  # if positive beat length, set as that
            pos = candidate

        if candidate[0] < time:
            cur = candidate
        else:  # exit since the timing point now occurs after the given time
            break

    return (pos[1], cur[1])

def _get_latest_positive_beat_length(timingPoints: list[tuple[int, float]], time: int) -> float:
    """Only gives the most recent positive (set) beat length"""
    most_recent = timingPoints[0][0]
    for candidate in timingPoints:
        if candidate[0] > time:
            break

        if candidate[1] > 0:
            most_recent = candidate[1]
    
    return most_recent
        
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

def _compute_slider_time_length(totalLength: float, beat_lengths: list[tuple[int, float]], 
                                time: int, sliderMult: float) -> float:
    """Calculates the length of time a slider exists for.
    TODO: do some tests
    """
    beatLength = _get_current_beat_length(beat_lengths, time)

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
        slider.lastPoint = (last_x, last_y)
        slider.lastX = last_x
        slider.lastY = last_y
    else:
        slider.lastPoint = (first_x, first_y)
        slider.lastX = first_x
        slider.lastY = first_y

    slider.sliderType = slider_type
    slider.numSlides = numSlides
    
    slider.sliderLength = sliderLength
    slider.totalSliderLength = numSlides * sliderLength
    time = int(parsed_cur[2])
    slider.timeLength = _compute_slider_time_length(slider.totalSliderLength, beat_lengths, 
                                                    time, sliderMult)
    slider.endTime = time + slider.timeLength

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

def _in_tolerance(input: float, target: float, tolerance: float) -> bool:
    """
    Meant for positive values. For target 1, tolerance 0.05, 0.95 to 1.05 is 
    acceptable.
    """
    return target * (1 - tolerance) <= input <= target * (1 + tolerance)

def _compute_attributes(info: MapInfo, beat_lengths: list[tuple[int, float]]) -> ComputedInfo:
    """
    Does more "advanced" computation using the map info and returns the computed information in a
    ComputedInfo object.
    """
    logging.info("Started computing attributes.")

    output = ComputedInfo(None, None, None, None)  # to be initialized
    timingDict = {
        'wholes': 0,
        'halves': 0,
        'thirds': 0,
        'fourths': 0,
        'sixths': 0,
        'eigths': 0,
        'twelfths': 0,
        'sixteenths': 0,
        'other': 0
    }

    timingPercents = OrderedDict()
    timingPercents['wholes'] = 0
    timingPercents['halves'] = 0
    timingPercents['thirds'] = 0
    timingPercents['fourths'] = 0
    timingPercents['sixths'] = 0
    timingPercents['eigths'] = 0
    timingPercents['twelfths'] = 0
    timingPercents['sixteenths'] = 0
    timingPercents['other'] = 0

    numObjects = len(info.hit_objects)
    
    totalTimeDiff = 0
    totalDistDiff = 0
    
    times = info.time_diffs
    for index, second in enumerate(info.hit_objects):

        if index == 0:
            continue
        
        # current beat length
        beatLength = _get_latest_positive_beat_length(beat_lengths, second.time)

        # time diff calculation
        first = info.hit_objects[index - 1]
        if isinstance(first, Slider) or isinstance(first, Spinner):
            timeDiff = second.time - first.endTime
        else: # circle
            timeDiff = times[index - 1]
            
        # print(timeDiff)
        if timeDiff < 2000:            
            totalTimeDiff += timeDiff
        else:
            numObjects -= 1
        
        # timing calculation
        timing = timeDiff / beatLength

        incremented = False
        for key, value in FRACTIONS.items():
            if incremented:
                break

            if _in_tolerance(timing, value, TIMING_TOLERANCE):
                timingDict[key] += 1
                incremented = True
            
        if not incremented:
            timingDict['other'] += 1
        
        # distance diff calculation
        if isinstance(first, Slider):
            totalDistDiff += math.sqrt((second.x - first.lastX) ** 2 + (second.y - first.lastY) ** 2)
        
        else:
            totalDistDiff += math.sqrt((second.x - first.x) ** 2 + (second.y - first.y) ** 2)

    
    for timingType in timingDict:
        timingPercents[timingType] = timingDict[timingType] / len(info.hit_objects) * 100  # multiply by 100 to make it a percent

    # time diff doesn't count objects with 2 second+ gap, but dist always counts
    # count the number of gaps, so one less than the number of counted objects
    avgTimeDiff = totalTimeDiff / (numObjects - 1)
    avgDist = totalDistDiff / (len(info.hit_objects) - 1)

    # assigning values
    output.avgDist = avgDist
    print(avgDist)
    output.avgTime = avgTimeDiff
    output.timingDict = timingDict
    output.timingPercents = timingPercents

    logging.info("Finished computing attributes.")
    # print(output)
    return output
    

def parse_osu(input_file_name: str, out, target: str):
    """Parses the osu formatted file and outputs it as a csv file."""
    logging.info(f"Started parsing file {input_file_name}.")
    # TODO apparently using with is better so change it
    in_file = open(input_file_name, encoding="utf8", mode='r')
    
    # first line is always version declaration
    version = in_file.readline()

    line = ''
    # read in difficulty
    difficulty = _read_difficulty(in_file)
    line += difficulty + ','

    sliderMult = float(difficulty.split(',')[4])
    
    # get list of beat lengths
    beat_lengths = _get_beat_lengths(in_file)

    info = _get_info(in_file, beat_lengths, sliderMult)
    computed = _compute_attributes(info, beat_lengths)
    
    # write the computed info to the csv
    line += str(computed.avgDist) + ','
    line += str(computed.avgTime) + ','

    timingPercents = computed.timingPercents
    for key, percent in timingPercents.items():
        line += str(percent) + ','

    # write the map classification answer
    line += target

    line += '\n'
    out.write(line)

    in_file.close()
    logging.info(f"Finished parsing file {input_file_name}.")
    return

def parse_target(out, target: str):
    targetDirectory = MAP_DIRECTORY + target + '/'
    for filename in os.listdir(targetDirectory):
        parse_osu(targetDirectory + filename, out, target)

    return

def parse_data():
    out = open("output.csv", 'w')
    out.write(OUTPUT_FILE_HEADER)

    parse_target(out, '0')  # jump
    parse_target(out, '1')  # stream

    out.close()
    return

if __name__ == "__main__":
    logging.basicConfig(filename='parser.log',filemode='w', level=logging.INFO, 
                        format='%(asctime)s - %(message)s', datefmt='%d-%b-%y %H:%M:%S')
    
    parse_data()

   