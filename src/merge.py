#!/usr/bin/python
from sys import argv
from seqtrace.core.stproject_io import SeqTraceProjReader, SeqTraceProjWriter


def merge_projects(argv):
    output = "all.str"
    outproject = SeqTraceProjWriter()
    index = 0
    names = []
    for filename in argv[1:len(argv)]:
        print(filename)
        project = SeqTraceProjReader()
        project.readFile(filename)
        if index == 0:
            settings = project.getConsensSeqSettings()
            outproject.setConsensSeqSettings(settings)
        for key, value in list(project.proj_data['properties'].items()):
            outproject.addProperty(key, value)
        index += 1
        for item in project:
            name = item.getName()
            if name in names:
                item.setName(name + "_a")
            names.append(item.getName())
            outproject.addProjectItem(item)
    outproject.write(output)


if __name__ == "__main__":
    merge_projects(argv)
