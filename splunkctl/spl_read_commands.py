"""Conservative built-in read commands from the Enterprise 10.0 reference.

Source: https://help.splunk.com/en/splunk-enterprise/spl-search-reference/10.0/quick-reference/command-quick-reference
Writers and commands that dispatch searches, scripts, REST calls or saved
searches are omitted. This is intentionally narrower than all built-ins.
"""

READ_COMMANDS = frozenset(
    """
abstract accum addcoltotals addinfo addtotals analyzefields anomalies
anomalousvalue anomalydetection append appendcols appendpipe arules associate
autoregress bin bucket bucketdir chart cluster cofilter concurrency contingency
convert correlate dbinspect dedup delta diff erex eval eventcount eventstats
extract kv fieldformat fields fieldsummary filldown fillnull findtypes folderize
format gauge gentimes geom geomfilter geostats head highlight history iconify
inputcsv inputlookup iplocation join kmeans kvform loadjob localize localop
makecontinuous makemv makeresults metadata metasearch mpreview msearch
mstats multikv mvcombine mvexpand nomv outlier overlap predict rangemap rare
redistribute regex reltime rename replace require return reverse rex rtorder
scrub search selfjoin set setfields sichart sirare sistats sitimechart sitop
sort spath stats strcat streamstats table tags tail timechart timewrap tojson
top transaction transpose trendline tstats typeahead typelearner typer uniq
untable walklex where x11 xmlkv xmlunescape xpath xyseries
""".split()
)
