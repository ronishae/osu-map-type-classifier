import csv
OUTPUT_FILE_HEADER = "HPDrainRate,CircleSize,OverallDifficulty,ApproachRate,SliderMultiplier,SliderTickRate\n"

def compute_diffs(input_file: str):
    differences = []
    previous_value = None

    with open(input_file, 'r') as file:
        reader = csv.reader(file)
        header = next(reader)  # Skip the header

        # Skip the first data point
        first_row = next(reader)
        previous_value = int(first_row[2])

        for row in reader:
            current_value = int(row[2])
            if previous_value is not None:
                difference = current_value - previous_value
                differences.append(difference)
            previous_value = current_value

    # Output the differences
    print("Differences between consecutive third column values:")
    for diff in differences:
        print(diff)

def _seek_to_section(in_file, section) -> None:
    """Jumps to the given section in the file (case sensitive).

    The next line read after this function will be the first line
    of that section.

    in_file -- the opened file to read
    section -- the name of the section
    """
    row = in_file.readline()
    while ("[" + section + "]") not in row:
        row = in_file.readline()

    return

def _read_difficulty(in_file) -> str:
    """Outputs a comma seperated string with the difficulty parameters.

    Assumes the file is in v14.osu format,
    and has not read past the difficulty section.
    
    in_file -- the opened file to read
    """
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
    _seek_to_section(in_file, "TimingPoints")
    beat_lengths = []

    row = in_file.readline()
    while row != '\n' and '[' not in row and ']' not in row:
        parsed = row.split(',')
        time = int(parsed[0])
        beat_length = float(parsed[1])

        if beat_length >= 0: # only want non-inherited beat lengths
            pair = (time, beat_length)
            beat_lengths.append(pair)
        row = in_file.readline()
    
    return beat_lengths

def _is_circle(num) -> bool:
    return num & 1

def _is_slider(num) -> bool:
    return num & 1 << 1

def _get_object_type(num) -> int:
    if _is_circle(num):
        return 0
    elif _is_slider(num):
        return 1
    else:
        return 2

def _calculate_distance(x1, y1, x2, y2, size) -> float:
    """Calculates edge to edge distance between circles"""
    # TODO: need to figure out circle size and pixel values
    return 0

def _get_info(in_file, beat_lengths):
    """Returns a list information on the hit objects in the map.

    Differences are calculated from the later object to the earlier object.

    The first element is a list of the x_difference.
    The second is a list of the y_difference.
    The third is a list of the distance between objects.
    The fourth is a list of the time difference.
    The fifth is a list of the object type (circle, slider, or spinner)
    The sixth is the number of B (Bezier) type sliders
    The seventh is the number of C (Centripetal catmull-rom) type sliders
    The eigth is the number of L (Linear) type sliders
    The ninth is the number of P (Perfect Circle) type sliders
    """
    # TODO: currently does not parse first object for adding to slider type
    # TODO: might want to do something with the slider points (maybe 
    # calculate distance using the last slider point)
    x_diff = []
    y_diff = []
    distance = []
    time_diff = []
    types = []
    B = 0
    C = 0
    L = 0
    P = 0

    _seek_to_section(in_file, "HitObjects")
    prev = in_file.readline()
    cur = in_file.readline()
    while cur != '':
        parsed_prev = prev.split(',')
        parsed_cur = cur.split(',')
        obj_type = int(parsed_cur[3])
        if _is_slider(obj_type):
            params = parsed_prev[5].split('|')
            if params[0] == 'B':
                B += 1
            elif params[0] == 'C':
                C += 1
            elif params[0] == 'L':
                L += 1
            else:
                P += 1

        x1 = float(parsed_prev[0])
        y1 = float(parsed_prev[1])
        x2 = float(parsed_cur[0])
        y2 = float(parsed_cur[1])
        x_diff.append(x2 - x1)
        y_diff.append(y2 - y1)
        distance.append(_calculate_distance(x1, y1, x2, y2, 0)) #todo add circle size
        time_diff.append(parsed_cur[2] - parsed_prev[2])
        types.append(_get_object_type(obj_type))
        
        prev = cur
        cur = in_file.readline()

    return (x_diff, y_diff, distance, time_diff, types, B, C, L, P)

def parse_osu(input_file_name):
    in_file = open(input_file_name, encoding="utf8", mode='r')
    out = open("output.csv", 'w')

    out.write(OUTPUT_FILE_HEADER)

    # first line is always version declaration
    version = in_file.readline()

    line = ''
    # read in difficulty
    line += _read_difficulty(in_file)
    
    # get list of beat lengths
    beat_lengths = _get_beat_lengths(in_file)
    print(beat_lengths)


    line += '\n'
    out.write(line)

    out.close()
    in_file.close()
    return

if __name__ == "__main__":
    input_file = "quaver.osu" 
    parse_osu(input_file)

