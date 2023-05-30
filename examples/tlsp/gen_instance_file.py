
INSTANCES = [
    '000_88_5',
    '001_88_5',
    '005_88_10',
    '006_88_10',
    '010_174_20',
    '011_174_20',
    '020_174_15',
    '025_174_30',
    '015_174_40',
    '030_174_60',
    '035_520_20',
    '040_520_40',
    '045_520_60',
    '050_782_60',
    '055_782_90'
]

data = []
data += [ '../instances/General/' + i for i in INSTANCES ]
data += [ '../instances/LabStructure/'+ i for i in INSTANCES ]
data += [ '../instances/RealWorld/2019-04' ]
data += [ '../instances/RealWorld/2019-07' ]
data += [ '../instances/RealWorld/2019-10' ]

for d in data:
    args = []

    args += ['--input file']
    args += ['--tasks', d + '_tasks.xml']
    args += ['--environment', d + '_environment.xml']
    args += ['--schedule', d + '_schedule.xml']

    with open('instances.txt', 'a') as file:
        file.write(' '.join(args))
        file.write('\n')
            

