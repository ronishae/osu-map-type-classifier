# osu-map-type-classifier

Classifies osu! maps as either jump or stream based on their map data. 

Currently 87.5% accurate based on this data.

Generates data from maps in map_data

0 = jump | 1 = stream

Running `data_parser.py` will produce `output.csv`, which is fed into `classifier.py`.


stream maps from https://osucollector.com/collections/9221/Stream

jump maps from https://osucollector.com/collections/10916/NM-Jump-Farm