import fnmatch, itertools, os, sys, re, types
import maya.cmds as cmds


class error(Exception):
	"""The exception raised in case of failures."""


def find(path, shellglobs=None, namefs=None, relative=True, findSubdir=True):
	"""
	Find files in the directory tree starting at 'path' (filtered by
	Unix shell-style wildcards ('shellglobs') and/or the functions in
	the 'namefs' sequence).

	Please not that the shell wildcards work in a cumulative fashion
	i.e. each of them is applied to the full set of file *names* found.

	Conversely, all the functions in 'namefs'
		- only get to see the output of their respective predecessor
		  function in the sequence (with the obvious exception of the
		  first function)
		- are applied to the full file *path* (whereas the shell-style
		  wildcards are only applied to the file *names*)

	@type path: string
	@param path: starting path of the directory tree to be searched
	@type shellglobs: sequence
	@param shellglobs: an optional sequence of Unix shell-style wildcards
	that are to be applied to the file *names* found
	@type namefs: sequence
	@param namefs: an optional sequence of functions to be applied to the
	file *paths* found
	@type relative: bool
	@param relative: a boolean flag that determines whether absolute or
	relative paths should be returned
	@rtype: sequence
	@return: paths for files found
	"""
	if not os.access(path, os.R_OK):
		raise error("cannot access path: '%s'" % path)

	fileList = [] # result list

	try:
		for dir, subdirs, files in os.walk(path):
			if not findSubdir and dir != path:
				continue
			if shellglobs:
				matched = []
				for pattern in shellglobs:
					filterf = lambda s: fnmatch.fnmatchcase(s, pattern)
					matched.extend(filter(filterf, files))
				fileList.extend(['%s%s%s' % (dir, os.sep, f) for f in matched])
			else:
				fileList.extend(['%s%s%s' % (dir, os.sep, f) for f in files])
		if not relative: fileList = map(os.path.abspath, fileList)
	 	if namefs:
	 		for ff in namefs: fileList = filter(ff, fileList)
	except Exception, e: raise error(str(e))
	return(fileList)


def findgrep(path, regexl, shellglobs=None, namefs=None,
			  relative=True, findSubdir=True, linenums=False, progressWin=False):
	"""
	Find files in the directory tree starting at 'path' (filtered by
	Unix shell-style wildcards ('shellglobs') and/or the functions in
	the 'namefs' sequence) and search inside these.

	Additionaly, the file content will be filtered by the regular
	expressions in the 'regexl' sequence. Each entry in the latter
	is a

		- either a string (with the regex definition)
		- or a tuple with arguments accepted by re.compile() (the
		  re.M and re.S flags will have no effect though)

	For all the files that pass the file name/content tests the function
	returns a dictionary where the

		- key is the file name and the
		- value is a string with lines filtered by 'regexl'

	@type path: string
	@param path: starting path of the directory tree to be searched
	@type shellglobs: sequence
	@param shellglobs: an optional sequence of Unix shell-style wildcards
		that are to be applied to the file *names* found
	@type namefs: sequence
	@param namefs: an optional sequence of functions to be applied to the
		file *paths* found
	@type relative: bool
	@param relative: a boolean flag that determines whether absolute or
		relative paths should be returned
	@type linenums: bool
	@param linenums: turns on line numbers for found files (like grep -n)
	@rtype: dict
	@return: file name (key) and lines filtered by 'regexl' (value)
	"""
	fileList = find(path, shellglobs=shellglobs,
					 namefs=namefs, findSubdir=findSubdir, relative=relative)
	if not fileList: return dict()

	result = dict()

	try:
		# first compile the regular expressions
		ffuncs = []
		for redata in regexl:
			if type(redata) == types.StringType or type(redata) == types.UnicodeType:
				ffuncs.append(re.compile(redata).search)
			elif type(redata) == types.TupleType:
				ffuncs.append(re.compile(*redata).search)
			else:
				raise error("'"+redata+"' incorrect type")
		if progressWin:
			cmds.progressWindow(t='File search', pr=0, ii=True, min=0, max=len(fileList))
		# now grep in the files found
		for file in fileList:
			# read file content
			fhandle = open(file, 'r')
			fcontent = fhandle.read()
			fhandle.close()
			# split file content in lines
			if linenums: lines = zip(itertools.count(1), fcontent.splitlines())
			else: lines = fcontent.splitlines()
			for ff in ffuncs:
				if linenums: lines = filter(lambda t: ff(t[1]), lines)
				else: lines = filter(ff, lines)
				# there's no point in applying the remaining regular
				# expressions if we don't have any matching lines any more
				if not lines: continue
			if progressWin:
				if cmds.progressWindow(q=True, ic=True): break
				cmds.progressWindow(e=True, pr=fileList.index(file))
			# the loop terminated normally; add this file to the
			# result set if there are any lines that matched
			if lines:
				if linenums:
					result[file] = '\n'.join(["%d:%s" % t for t in lines])
				else:
					result[file] = '\n'.join(map(str, lines))
	except Exception, e: raise error(str(e))
	if progressWin:
		cmds.progressWindow(ep=True)
	return(result)


def replace(path, regexl, shellglobs=None, namefs=None, bext='.bak'):
	"""
	Find files in the directory tree starting at 'path' (filtered by
	Unix shell-style wildcards ('shellglobs') and/or the functions in
	the 'namefs' sequence) and perform an in-place search/replace
	operation on these.

	Additionally, an in-place search/replace operation is performed
	on the content of all the files (whose names passed the tests)
	using the regular expressions in 'regexl'.

	Please note: 'regexl' is a sequence of 3-tuples, each having the
	following elements:

		- search string (Python regex syntax)
		- replace string (Python regex syntax)
		- regex flags or 'None' (re.compile syntax)

	Copies of the modified files are saved in backup files using the
	extension specified in 'bext'.

	@type path: string
	@param path: starting path of the directory tree to be searched
	@type shellglobs: sequence
	@param shellglobs: an optional sequence of Unix shell-style wildcards
		that are to be applied to the file *names* found
	@type namefs: sequence
	@param namefs: an optional sequence of functions to be applied to the
		file *paths* found
	@rtype: number
	@return: total number of files modified
	"""
	fileList = find(path, shellglobs=shellglobs, namefs=namefs)

	# return if no files found
	if not fileList: return 0

	filesChanged = 0

	try:
		cffl = []
		for searchs, replaces, reflags in regexl:
			# prepare the required regex objects, check whether we need
			# to pass any regex compilation flags
			if reflags is not None: regex = re.compile(searchs, reflags)
			else: regex = re.compile(searchs)
			cffl.append((regex.subn, replaces))
		for file in fileList:
			# read file content
			fhandle = open(file, 'r')
			text = fhandle.read()
			fhandle.close()
			substitutions = 0
			# unpack the subn() function and the replace string
			for subnfunc, replaces in cffl:
				text, numOfChanges = subnfunc(replaces, text)
				substitutions += numOfChanges
			if substitutions:
				# first move away the original file
				bakFileName = '%s%s' % (file, bext)
				if os.path.exists(bakFileName): os.unlink(bakFileName)
				os.rename(file, bakFileName)
				# now write the new file content
				fhandle = open(file, 'w')
				fhandle.write(text)
				fhandle.close()
				filesChanged += 1
	except Exception, e: raise error(str(e))

	# Returns the number of files that had some of their content changed
	return(filesChanged)
