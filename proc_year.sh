#!/bin/bash
# Script to be run overnight that will spin through a year's rawacf info..

echo Enter a year whose data you would like processed...
read year

for month in `seq 11 12`;
do
    echo $year-$month
    ./parse.py -y $year -m $month
    export archive=data/$year-$month
    mkdir $archive
    mv *.log $archive/
    mv bad*.txt $archive/
    cp superdarntimes.sqlite $archive/
done 
