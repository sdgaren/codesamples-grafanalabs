#!/usr/bin/env python
# -*- coding: utf-8 -*-

# Version 1.3.5

"""
This script was designed as part of consulting work and has been anonymized
somewhat for your review. The client had the following need - they were
receiving volumes of exception reports on a daily basis that needed to be
combined together into a single CSV for reporting, analysis, and prioritization
of work. But, they had a few issues to solve:

1. The reports arrived in a semi-structured format, with meaningful metadata at
   top, a table of one structure with varying length, then a second table of a
   different structure with consistent length. Excel could not make heads or
   tails of this format.
2. Even if Excel could have interpreted the layout, they came in with text
   encoding issues and with lots of malformed e-mail header noise in the body
   of the report. This caused Excel to crash when attempting to open the file.
3. The layout, text encoding issues, and e-mail header noise were not fully
   predictable, making any kind of automated cleanup process difficult and
   preventing basic attempts at parsing.
4. The file names the reports came in with were inconsistent and malformed.
   File names such as "MRRReport.txt.20210101" where part of the intended file
   name came after the file extension were not uncommon but not universal.
5. The team producing the defective reports had a multi-year backlog before
   they were willing to look into the defect.
6. The count of reports needing to be processed each day far exceeded the
   capacity of any reasonable manual process.

The below script was created to handle the above. The script reads a drop
folder looking for any number of these files, then looks for specific strings
that were known to reliably survive the text encoding issues. This helps the
script "get its bearings" within the file and find both the metadata outside
the table structures and the position of each table structure themselves. The
script then parses this data into an array and repeats for the next file,
alerting the user as it processes to any reports that have an unusual layout or
potentially missing / unparseable data. The client had very specific
requirements for the output CSV from this process, so a custom CSV output
routine was created to accommodate. Instructional comments are left throughout
to assist the client with maintenance of this script long-term.

A sample input file is also available for your review in the /reports folder
and a sample CSV complient with the client's requirements is available at
output.csv.

-Samuel Garen
206 351 8258
sdgaren@gmail.com
"""

# Modules
import csv
import datetime
import glob
import math
import os
import sys

# Variables
csvFileName = "output.csv"  # This is the file name for the CSV output.
pathToReportsFolder = "reports"  # This is the path to the folder where the Missing Register Readings reports are dropped to be processed by this script.
searchArray = ["Total number of PODs requested - On Cycle",
               "Number of PODs OC with readings provided for entire configuration",
               "Total number of PODs requested - Exceptions",
               "Number of PODs EXC with readings provided for entire configuration",
               "Number of PODs EXC with no readings provided at all",
               "Number of PODs EXC with actual readings provided",
               "Number of PODs EXC with estimated readings provided"]  # These are the strings to search for in the Missing Register Readings reports, in the order you want them put into the CSV file from left to right. Column headings below will want to correspond (but do not need to match exactly).
csvHeadingArray = ["Cycle",
                   "Total Number of PODs Requested on Cycle",
                   "Number of PODs with Readings - Entire Config (On Cycle)",
                   "Total Number of PODs Requested - Exceptions",
                   "Number of PODs EXC with Readings Provided for Entire Configuration",
                   "Estimated Readings Provided - Exceptions",
                   "Actual Readings Provided - Exceptions",
                   "No Readings Provided at All (Exceptions)"]  # This is the list of column headings in the CSV file from left to right.
reportFileMonthsArray = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV",
                         "DEC"]  # The Missing Register Readings reports have their months indicated as three-letter abbreviations. These are those abbreviations, which are needed to look up what month each data file corresponds to. If you wind up with reports from a particular month that aren't finding their way into the CSV file at the end, check first whether the Missing Register Readings reports have changed the date format shown in them.
cyclesPerBillingMonth = 21  # This is the number of cycles in a billing month. This helps the script understand the relationship between calendar months and billing months.
negativeAnswers = ["n", "no"]  # Negative answers the user can enter to prompts.
positiveAnswers = ["y", "yes"]  # Positive answers the user can enter to prompts.


# Functions

# Scans a given folder for text files matching given criteria and returns an array of those files.
def arrayOfFiles(criteria):
    try:
        fileArray = list(glob.glob(criteria))
    except:
        print("Unable to read directory. Exiting.")
        sys.exit()
    return fileArray


# Strips file path from file names for human-readable reporting and truncates long names so print functions don't wrap on 80-character terminals.
def truncatedFileName(fileName, path, maxLength):
    if len(fileName) > maxLength:
        fileName = fileName[len(path):math.floor((maxLength - 3) / 2) + len(path)] + "..." + fileName[len(fileName) - math.floor((maxLength - 3) / 2):]
    else:
        fileName = fileName[len(path):]
    return fileName


# Cleanly wraps string to width of terminal display.
def wordWrap(string):
    try:
        terminalWidth = (os.get_terminal_size()).columns
    except:
        terminalWidth = 80
    i = terminalWidth + 1
    while len(string) > terminalWidth:
        i -= 1
        if string[i] == " ":
            print(string[:i])
            string = string[i + 1:]
            i = terminalWidth + 1
        if i == terminalWidth - 30:
            print(string[:terminalWidth])
            string = string[terminalWidth + 1:]
            i = terminalWidth + 1
    if len(string) > 0:
        print(string)


# Main program

# Determine operating system and set path separator as appropriate.
if os.name in ["posix"]:
    pathSeparator = "/"
elif os.name in ["nt"]:
    pathSeparator = "\\"
else:
    print("")
    wordWrap("Operating system not supported. Exiting.")
    print("")
    sys.exit()

# Search through Reports folder and build an array of file names.
fileArray = arrayOfFiles(pathToReportsFolder + pathSeparator + "*.*")

# Tell user what was found.
print("")
if len(fileArray) == 1:
    wordWrap("1 report found.")
elif len(fileArray) > 1:
    wordWrap(str(len(fileArray)) + " reports found.")
else:
    wordWrap("No reports found. Exiting.")
    sys.exit()

# Build empty matrix to place search results into. Since the reports could come in in any order, later we'll use the matrix row number as an index of billing month and cycle, so row 619 belongs to cycle 19 for the billing month of June, and so forth. This will keep all the data organized by billing month and cycle for when it is put in the CSV file.
outputMatrix = [["" for column in range(len(searchArray) + 3)] for row in range(0, 1300)]
for i in range(1, 13):
    for j in range(0, 100):
        outputMatrix[i * 100 + j][0] = i

# Iterate over the array of reports.
for file in fileArray:

    # Open report file.
    try:
        with open(file, "r") as reportFile:
            searchLines = reportFile.readlines()
    except:
        wordWrap("Unable to open " + file + ". Exiting.")
        sys.exit()

    # Fill resultsArray with error indicators in case nothing is found in the search. These will be overwritten with actual values as the script runs and will only be seen if the search fails to find values from searchArray.
    resultsArray = []
    for i in range(0, len(searchArray)):
        resultsArray.append("Missing")

    # Search report file for relevant strings from searchArray.
    for i, line in enumerate(searchLines):

        # Parse out what read cycle this file corresponds to.
        if "Read Cycle {" in line:
            try:
                readCycle = int(line[39:41])
            except:
                print("")
                wordWrap(
                    file + " appears to not have a read cycle. If this report file has no read schedule, this is normal.")
                readCycle = 0

        # Parse out what day and month the data in this file is from.
        if "Schedule Dates" in line:
            try:
                reportFileDay = int(line[46:48])
                reportFileMonth = reportFileMonthsArray.index(line[49:52]) + 1
                reportFileYear = 2000 + int(line[53:55])  # Your friendly local consultant recommends not trying to run this report on MRRs from the 1900s and hopes this script is unnecessary by the year 2100, as century is not detectable in the date strings provided.
            except:
                print("")
                wordWrap(
                    file + " appears to not have a schedule date. If this report file has no read schedule, this is normal.")
                reportFileDay = 0
                reportFileMonth = 0

        # Scan report file for items in searchArray and dump the entire line to resultsArray if found
        for j in range(0, len(searchArray)):
            if searchArray[j] in line:
                resultsArray[j] = line

    reportFile.close()

    # Remove the text labels in the reports file from resultsArray by truncating the labels and whitespace off the front of the string and converting to an integer. If you're getting parsing errors, the likelihood is this section needs to be updated.
    for i in range(0, len(resultsArray)):
        if resultsArray[i] != "Missing":
            tempString = resultsArray[i]
            try:
                resultsArray[i] = int(tempString[73:])
            except:
                print("")
                wordWrap("Invalid data. Report format may have changed.")
                sys.exit()

    # Since billing cycles don't perfectly line up with the months of the year, try to figure out what billing month this data belongs to. Look for a combination of a date late in the month and a low cycle number, in which case we guess that the cycle actually belongs to the following billing month, or a date early in the month and a high cycle number, in which case we guess that the cycle actually belongs to the previous billing month. If the date and cycle number are close to one another, guess that the billing month and actual month are the same. If the file has no schedule day, this also implies that the file does not carry any data and no determination needs to be made, as nothing from this file will be exported to the resultant CSV.
    if reportFileDay > 0:
        if (reportFileDay < 10) and (readCycle > 10):
            billingMonth = reportFileMonth - 1
        elif (reportFileDay > cyclesPerBillingMonth - 1) and (readCycle < 10):
            billingMonth = reportFileMonth + 1
        else:
            billingMonth = reportFileMonth

        # Report interpretation of read cycle and billing month to user
        print("")
        wordWrap("Data in " + file + " found for " + datetime.date(1900, reportFileMonth, 1).strftime('%B') + " " + str(
            reportFileDay) + ", " + str(reportFileYear) + ", cycle " + str(
            readCycle) + ". Report interpreted for " + datetime.date(1900, billingMonth, 1).strftime(
            '%B') + " billing month.")

        print("")
        print("Working...")

        # Put results into appropriate row in outputMatrix
        for i in range(0, len(resultsArray)):
            outputMatrix[billingMonth * 100 + readCycle][i + 1] = resultsArray[i]
            outputMatrix[billingMonth * 100 + readCycle][len(resultsArray) + 2] = 1 #Insert a flag in the rightmost column to indicate that this row in the array carries actual data

# Scan through outputMatrix and see which months actually have data so that the CSV file ends up with only months for which there is data
outputMonthsArray = []
for i in range(0, len(outputMatrix)):
    if outputMatrix[i][len(resultsArray) + 2] == 1:
        if outputMatrix[i][0] not in outputMonthsArray:
            outputMonthsArray.append(outputMatrix[i][0])

# Build CSV output file according to client specifications
try:
    with open(csvFileName, "w") as csvOutputFile:
        writer = csv.writer(csvOutputFile, delimiter=",", dialect="excel")

        # Build outputArray which will receive data from outputMatrix one line at a time.
        outputArray = []
        for i in range(0, len(resultsArray) + 1):
            outputArray.append("")

        # Iterate through outputMatrix and place data in CSV file with human-readable formatting.
        for month in outputMonthsArray:
            for cycle in range(1, cyclesPerBillingMonth + 1):
                for column in range(0, len(resultsArray) + 1):
                    # Fill outputArray with data from the appropriate row in outputMatrix.
                    outputArray[column] = outputMatrix[month * 100 + cycle][column]

                    # Fill in the first position in the array with the cycle number.
                    outputArray[0] = cycle

                # At the top of each month, add the name of the month and the column names from csvHeadingArray.
                if cycle == 1:
                    writer.writerow([datetime.date(1900, month, 1).strftime('%B')])
                    writer.writerow(csvHeadingArray)

                # Check to see whether the rightmost column has been flagged as carrying actual data. If so, write contents to the CSV file. If not, write the cycle number of leave the remainder of the row blank. This indicates that a file was found for the month / cycle shown, but that it did not carry valid data.
                if outputMatrix[month * 100 + cycle][len(resultsArray) + 2] == 1:
                    writer.writerow(outputArray)
                else:
                    writer.writerow([cycle] + [""] * (len(resultsArray)))

                # If we've hit the end of a billing month, put in a blank line to separate it from the following month.
                if cycle == cyclesPerBillingMonth:
                    writer.writerow([""])
except:
    wordWrap("Unable to open or create " + csvFileName + ". Exiting.")
    sys.exit()

# Save and close the CSV file.
csvOutputFile.close()

# Alert user to check CSV file for accuracy.
print("")
wordWrap(csvFileName + " created successfully.")
print("")

# Offer to clean up the Data subfolder if the CSV file is accurate.
choice = ""
while choice not in negativeAnswers + positiveAnswers:

    # If the user selects "yes", clear out the Data subfolder.
    choice = input("Would you like to empty the /" + pathToReportsFolder + " folder? [Y/N]: ").lower()

    if choice in positiveAnswers:
        fileArray = arrayOfFiles(pathToReportsFolder + pathSeparator + "*txt.*")
        for file in fileArray:
            os.remove(file)
        print("")
        wordWrap("/" + pathToReportsFolder + " folder cleared out successfully.")

    # If the user selects "no", tell them they'll have to do it themselves before running the script again.
    elif choice in negativeAnswers:
        print("")
        wordWrap(pathToReportsFolder + " folder not emptied.")

print("")
print("All done!")
print("")