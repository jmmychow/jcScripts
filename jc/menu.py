# menu.py
# This is a Python class wrapper implementing Maya's menu system.
#
# Installation:
# This file is supposed to be the module called jc.menu.
# Under Maya script directory, create a directory called 'jc', put an empty file '__init__.py' and this file under there.
# Add PYTHONPATH to point to script directory in Maya.env.
#
# URL:
# http://sites.google.com/site/cgriders/jc/menu
#


from types import *
from math import *
from random import *
from re import *
import types, os, random, re, copy, csv, traceback, sys
import maya.cmds as cmds
import maya.mel as mel
import jc.files


__moduleName = "jc.menu"

__menus = {}
__callbacks = {}


def createMenu(name, parent='MayaWindow'):
	if not parent:
		parent = 'MayaWindow'
	if isinstance(parent, types.StringType) or isinstance(parent, types.UnicodeType):
		if cmds.window(parent, ex=True):
			__menus[name] = menu(name, parent)
			return __menus[name]
		elif parent in __menus:
			return subMenuItem(__menus[parent], name)
	elif isinstance(parent, menu):
		return subMenuItem(parent, name)
	parent = 'MayaWindow'
	__menus[name] = menu(name, parent)
	return __menus[name]


def destroyMenu(name):
	if name and name in __menus:
		__menus.pop(name)
	else:
		for n,m in __menus.items():
			m.delName(name)


def setCallback(id, method):
	__callbacks[id] = method


def removeCallback(id):
	if id and id in __callbacks:
		__callbacks.pop(id)


def callback(id):
	if id and id in __callbacks:
		__callbacks[id]()


def	getMenus():
	return __menus.keys()


class menu:

	__parent = None
	__id = None
	__name = None
	__items = {}


	def __init__(self, name, parent='MayaWindow'):
		self.__parent = parent
		self.__name = name
		self.__id = None
		if parent:
			self.__id = cmds.menu(p=parent, l=compile("(?:[\w|\s|\.]*\|)*(?P<last>[\w|\s|\.]*)").match(name).group('last'), to=True, aob=True)
		self.__items = {}


	def __del__(self):
		for i in self.__items.keys():
			if isinstance(self.__items[i], commandItem):
				if self.__items[i].getOptionId():
					removeCallback(self.__items[i].getOptionId())
				removeCallback(self.__items[i].getId())
			elif isinstance(self.__items[i], subMenuItem) and self.__items[i].getName():
				destroyMenu(self.__items[i].getName())
		self.__items.clear()
		if self.__id and cmds.menu(self.__id, q=True, exists=True):
			cmds.deleteUI(self.__id)


	def addItem(self, i):
		id = i.getId()
		if id in self.__items:
			self.__items.pop(id)
		self.__items[id] = i


	def	delItem(self, id):
		id = i.getId()
		if id in self.__items:
			self.__items.pop(id)


	def	delName(self, name):
		for n,m in self.__items.items():
			#if cmds.menuItem(n, q=True, ex=True) and cmds.menuItem(n, q=True, l=True) == name:
			try:
				typ = cmds.objectTypeUI(n)
			except:
				continue
			if typ == "subMenuItem" and cmds.menuItem(n, q=True, l=True) == name:
				self.__items.pop(n)

	def getId(self):
		return self.__id


	def	getName(self):
		return self.__name
		

class item:

	__id = None


	def __init__(self, id):
		self.__id = id


	def getId(self):
		return self.__id


class dividerItem(item):

	def __init__(self, parent):
		item.__init__(self, cmds.menuItem(d=True, p=parent.getId()))
		parent.addItem(self)


	def __del__(self):
		id = item.getId(self)
		if id and cmds.menuItem(id, q=True, ex=True):
			cmds.deleteUI(id, mi=True)


class subMenuItem(item, menu):

	def __init__(self, parent, name):
		item.__init__(self, cmds.menuItem(l=name, sm=True, p=parent.getId(), to=True, aob=True))
		menu.__init__(self, name, None)
		parent.addItem(self)

	def __del__(self):
		menu.__del__(self)
		id = item.getId(self)
		if id and cmds.menuItem(id, q=True, ex=True):
			cmds.deleteUI(id, mi=True)


	def getId(self):
		return item.getId(self)


class commandItem(item):

	__name = None
	__display = None
	__optionId = None
	__options = None
	__parentId = None
	__echo = False


	def __init__(self, parent, commandName, displayName, echo=False, annotation=''):
		# Sometime this fails to create menu item
		# item.__init__(self, cmds.menuItem(l=displayName, p=parent.getId()))

		# Just because the above statement would sometimes fail, I must specify menu name and create it with c option
		# Note that menuItem will return an ID which is equal to the given ID prefixed with its predecessors separated by "|"
		
		# Test if the menuItem exists with the generated ID
		while(True):
			id = "command" + str(randint(1,9999))
			if cmds.menuItem(id, q=True, ex=True):
				continue
			try:
				cmds.objectType(id)
				continue
			except:
				break

		id = cmds.menuItem(id, l=displayName, p=parent.getId(), c="jc.menu.callback(\""+parent.getId()+"|"+id+"\")", ann=annotation)
		item.__init__(self, id)

		setCallback(id, self.performCommand)
		# If menu item fails to create, this statment won't work
		# cmds.menuItem(id, e=True, c="jc.menu.callback(\""+id+"\")")

		self.__name = commandName
		self.__display = displayName
		self.__parentId = parent.getId()	# don't store 'parent' itself, otherwise there would be a cycle and the parent menu won't get destroyed
		self.__echo = echo
		parent.addItem(self)


	def __del__(self):
		if isinstance(self, item):
			id = item.getId(self)
			# removeCallback(id)	callback should be removed before destruction of command item
			if id and cmds.menuItem(id, q=True, ex=True):
				cmds.deleteUI(id, mi=True)
		if self.__optionId:
			# removeCallback(self.__optionId)	callback should be removed before destruction of command item
			if cmds.menuItem(self.__optionId, q=True, ex=True):
				cmds.deleteUI(self.__optionId, mi=True)


	def	getEcho(self):
		return self.__echo


	def getName(self):
		return self.__name

		
	def	getOptions(self):
		return self.__options


	def addOption(self, o):
		if not self.__options:
			self.__options = []

			# The ia option doesn't work
			# self.__optionId = cmds.menuItem(ob=True, ia=item.getId(self))

			# Test if the menuItem exists with the generated ID
			while(True):
				id = "option" + str(randint(1,9999))
				try:
					cmds.objectType(id)
					continue
				except:
					break

			self.__optionId = cmds.menuItem(id, ob=True, c="jc.menu.callback(\""+self.__parentId+"|"+id+"\")")
			setCallback(self.__optionId, self.showOptions)

		self.__options.append(o)


	def	getOptionId(self):
		return self.__optionId
		
		
	def setOptionVars(self, default):
		if self.__options:
			for o in self.__options:
				o.setupVar(default)


	def performCommand(self):
		self.setOptionVars(False)

		cmd = self.__name

		# special usage: igonre options if commandName contains arguments
		if not compile("[\w|\.]+\((.*)\)$").search(cmd):
			cmd += "("
			if self.__options:
				def allPositional(x): return x.positional
				for o in filter(allPositional, self.__options):
					(name,value) = o.getValue()
					if isinstance(value, types.ListType):
						cmd += '['
						for v in value:
							cmd += '"'+v+'",'
						cmd = cmd.strip(',')
						cmd += ']'
					else:
						cmd += str(value)
					cmd += ','

				def allNonPositional(x): return not x.positional
				for o in filter(allNonPositional, self.__options):
					(name,value) = o.getValue()
					cmd += name + '='
					if isinstance(value, types.ListType):
						cmd += '['
						for v in value:
							cmd += '"'+v+'",'
						cmd = cmd.strip(',')
						cmd += ']'
					else:
						cmd += str(value)
					cmd += ','

				cmd = cmd.strip(',')
			cmd += ")"

		try:
			if self.__echo:
				print cmd
			mel.eval('python("' + cmd.replace('"','\\"') + '")')
		except RuntimeError, (strerror):
			# load module if it's not yet loaded
			buffer = "%s" % strerror
			module = re.compile("NameError: name '(\w+)' is not defined", re.M).findall(buffer)
			if module:
				cmd = "import "+module[0]+"\\n"+cmd
				mel.eval('python("' + cmd.replace('"','\\"') + '")')


	def setOptions(self):
		self.callback(0)

	def resetOptions(self):
		self.callback(1)

	def saveOptions(self):
		self.callback(2)

	def executeOptions(self):
		self.callback(3)


	def callback(self, action):
		# action: 0=current, 1=reset, 2=save or 3=execute

		if action < 2:
			self.setOptionVars(action)

		if self.__options:
			for o in self.__options:
				if action < 2:
					o.updateUI()
				else:
					o.updateVar()

		if action == 3:
			self.performCommand()


	def showOptions(self):

		#	Step 1:  Get the option box.
		cmds.setParent(mel.eval("getOptionBox()"))

		#	Step 2:  Pass the command name to the option box.
		mel.eval("setOptionBoxCommandName(\""+self.__name+"\")")

		#	Step 3:  Activate the default UI template.
		cmds.setUITemplate("DefaultTemplate", pushTemplate=True)

		#	Step 4: Create option box contents.
		cmds.waitCursor(state=True)
		layout = cmds.columnLayout(adjustableColumn=True)
		cmds.columnLayout()

		if self.__options:
			for o in self.__options:
				o.showUI(layout)

		cmds.setParent('..')
		cmds.setParent('..', menu=True)
		cmds.waitCursor(state=False)


		#	Step 5: Deactivate the default UI template.
		cmds.setUITemplate(popTemplate=True)

		#	Step 6: Customize the buttons.  
		btn = mel.eval("getOptionBoxApplyBtn()")
		setCallback(btn, self.executeOptions)
		cmds.button(
			btn,
			edit=True,
			label="Apply",
			command="jc.menu.callback(\""+btn+"\")")
		
		btn = mel.eval("getOptionBoxApplyAndCloseBtn()")
		setCallback(btn, self.executeOptions)
		cmds.button(
			btn,
			edit=True,
			label=self.__display,
			command="jc.menu.callback(\""+btn+"\")\nimport maya.mel\nmaya.mel.eval(\"hideOptionBox\")")

		btn = mel.eval("getOptionBoxSaveBtn()")
		setCallback(btn, self.saveOptions)
		cmds.button(
			btn,
			edit=True,
			command="python(\"jc.menu.callback(\\\""+btn+"\\\")\")")

		btn = mel.eval("getOptionBoxResetBtn()")
		setCallback(btn, self.resetOptions)
		cmds.button(
			btn,
			edit=True,
			command="python(\"jc.menu.callback(\\\""+btn+"\\\")\")")


		#	Step 7: Set the option box title.
		mel.eval("setOptionBoxTitle(\""+self.__display+" Options\")")

		#	Step 8: Customize the 'Help' menu item text.
		mel.eval("setOptionBoxHelpTag(\"Help on "+self.__display+" Options\")")

		# TBD: showHelp

		#	Step 9: Set the current values of the option box.
		self.setOptions()

		#	Step 10: Show the option box.
		mel.eval("showOptionBox()")


class melItem(commandItem):

	def	performCommand(self):
		self.setOptionVars(False)

		cmd = commandItem.getName(self)

		# special usage: igonre options if commandName contains arguments
		if not compile("[\w|\.]+\((.*)\)$").search(cmd):
			cmd += " "
			options = commandItem.getOptions(self)
			if options:
				def allPositional(x): return x.positional
				for o in filter(allPositional, options):
					(name,value) = o.getValue()
					if isinstance(value, types.ListType):
						cmd += '{'
						for v in value:
							cmd += '"'+v+'",'
						cmd = cmd.strip(',')
						cmd += '}'
					else:
						cmd += str(value)
					cmd += ' '

				def allNonPositional(x): return not x.positional
				for o in filter(allNonPositional, options):
					(name,value) = o.getValue()
					cmd += '-'+name + ' '
					if isinstance(value, types.ListType):
						cmd += '{'
						for v in value:
							cmd += '"'+v+'",'
						cmd = cmd.strip(',')
						cmd += '}'
					else:
						cmd += str(value)
					cmd += ' '

				cmd = cmd.strip()

		try:
			if commandItem.getEcho(self):
				print cmd
			mel.eval(cmd)
		except RuntimeError:
			# ignore runtime error of mel
			pass


class option:

	__parent = None
	__name = None
	__shortName = None
	positional = True

	id = None
	__dispName = None
	__varName = None

	__default = None
	value = None


	def __init__(self, parent, name, default, share=False, short=None, positional=False):
		self.__parent = parent
		self.__name = name.replace(' ','')
		self.__shortName = short
		self.positional = positional

		self.__dispName = name[0].upper() + name[1:]

		if share and isinstance(parent, commandItem):
			commandName = parent.getName()
			self.__varName = commandName[0:commandName.rfind('.')]+'.'+self.__name
		else:
			self.__varName = parent.getName()+'.'+self.__name

		self.__default = default
		self.value = self.setupVar(False)

		parent.addOption(self)


	def getDisplayName(self):
		return self.__dispName


	def getVarName(self):
		return self.__varName


	def getName(self):
		if self.__shortName:
			return self.__shortName
		return self.__name


	def setupVar(self, default):
		if default or not cmds.optionVar(ex=self.__varName):
			self.value = self.__default
		pair = ( self.__varName, self.value )
		if default or not cmds.optionVar(ex=self.__varName):
			self.setupVarSub(pair)
		return cmds.optionVar(q=self.__varName)


	def updateUI(self):
		if self.id and cmds.optionVar(ex=self.__varName):
			self.value = cmds.optionVar(q=self.__varName)
			self.updateUISub()


	def getValue(self):
		self.updateVar()
		if cmds.optionVar(ex=self.__varName):
			self.value = cmds.optionVar(q=self.__varName)
		return self.getValueSub()


class integerOption(option):

	__min = None
	__max = None


	def __init__(self, parent, name, default, share=False, short=None, positional=False):
		option.__init__(self, parent, name, default, share=share, short=short, positional=positional)
		try:
			self.value = int(self.value)
		except:
			self.setupVar(True)

		if self.value >= 0 and self.value <= 1:
			self.__max = 1000
		else:
			self.__max = pow(10, 1 + modf(log10(abs(self.value)))[1])*1000
		self.__min = -self.__max


	def setupVarSub(self, pair):
		cmds.optionVar(iv=pair)


	def showUI(self, layout):
		self.id = cmds.intSliderGrp(l=self.getDisplayName(), p=layout, v=self.value, min=self.__min, max=self.__max, fmn=self.__min, fmx=self.__max)


	def updateUISub(self):
		cmds.intSliderGrp(self.id, e=True, v=self.value)


	def updateVar(self):
		if self.id and cmds.intSliderGrp(self.id, ex=True):
			cmds.optionVar(iv=[ self.getVarName(), cmds.intSliderGrp(self.id, q=True, v=True) ])


	def getValueSub(self):
		return ( self.getName(), self.value )


class floatOption(option):

	__min = None
	__max = None


	def __init__(self, parent, name, default, share=False, short=None, positional=False):
		option.__init__(self, parent, name, default, share=share, short=short, positional=positional)
		try:
			self.value = float(self.value)
		except:
			self.setupVar(True)

		if self.value >= 0 and self.value <= 1:
			self.__min = 0
			self.__max = 1
		else:
			self.__max = pow(10, 1 + modf(log10(abs(self.value)))[1])
			if self.value >= 0:
				self.__min = 0
			else:
				self.__min = -self.__max


	def setupVarSub(self, pair):
		cmds.optionVar(fv=pair)


	def showUI(self, layout):
		self.id = cmds.floatSliderGrp(l=self.getDisplayName(), p=layout, v=self.value, min=self.__min, max=self.__max, fmn=self.__min, fmx=self.__max*100)


	def updateUISub(self):
		cmds.floatSliderGrp(self.id, e=True, v=self.value)


	def updateVar(self):
		if self.id and cmds.floatSliderGrp(self.id, ex=True):
			cmds.optionVar(fv=[ self.getVarName(), cmds.floatSliderGrp(self.id, q=True, v=True) ])


	def getValueSub(self):
		return ( self.getName(), self.value )


class booleanOption(option):

	def __init__(self, parent, name, default, share=False, short=None, positional=False):
		option.__init__(self, parent, name, default, share=share, short=short, positional=positional)
		try:
			self.value = bool(self.value)
		except:
			self.setupVar(True)


	def setupVarSub(self, pair):
		cmds.optionVar(iv=pair)


	def showUI(self, layout):
		self.id = cmds.checkBoxGrp(l=self.getDisplayName(), p=layout, v1=self.value, h=22)


	def updateUISub(self):
		cmds.checkBoxGrp(self.id, e=True, v1=self.value)


	def updateVar(self):
		if self.id and cmds.checkBoxGrp(self.id, q=True, ex=True):
			cmds.optionVar(iv=[ self.getVarName(), cmds.checkBoxGrp(self.id, q=True, v1=True) ])


	def getValueSub(self):
		return ( self.getName(), self.value )


class stringOption(option):

	def __init__(self, parent, name, default, share=False, short=None, positional=False):
		option.__init__(self, parent, name, default, share=share, short=short, positional=positional)
		try:
			self.value = str(self.value)
		except:
			self.setupVar(True)


	def setupVarSub(self, pair):
		cmds.optionVar(sv=pair)


	def showUI(self, layout):
		self.id = cmds.textFieldGrp(l=self.getDisplayName(), p=layout, tx=self.value)


	def updateUISub(self):
		cmds.textFieldGrp(self.id, e=True, tx=self.value)


	def updateVar(self):
		if self.id and cmds.textFieldGrp(self.id, ex=True):
			cmds.optionVar(sv=[ self.getVarName(), cmds.textFieldGrp(self.id, q=True, tx=True) ])


	def getValueSub(self):
		return ( self.getName(), '"'+self.value+'"' )


class listOption(option):

	__listCallback = None


	def __init__(self, parent, name, default, listCallback, share=False, short=None, positional=False):
		option.__init__(self, parent, name, default, share=share, short=short, positional=positional)
		self.__listCallback = listCallback
		try:
			self.value = str(self.value)
		except:
			self.setupVar(True)


	def setupVarSub(self, pair):
		cmds.optionVar(sv=pair)


	def showUI(self, layout):
		list = self.__listCallback
		if callable(self.__listCallback):
			list = self.__listCallback()
		if isinstance(list, types.ListType) and len(list) > 0:
			self.id = cmds.optionMenuGrp(l=self.getDisplayName(), p=layout, h=32)
			for i in list:
				cmds.menuItem(l=i)
			cmds.setParent('..')
			if self.value in list:
				cmds.optionMenuGrp(self.id, e=True, v=self.value)
			else:
				cmds.optionMenuGrp(self.id, e=True, sl=1)
				self.updateVar()
		else:
			self.id = cmds.optionMenuGrp(l=self.getDisplayName(), p=layout, h=32)


	def updateUISub(self):
		list = cmds.optionMenuGrp(self.id, q=True, ill=True)
		if list:
			for i in list:
				if self.value == cmds.menuItem(i, q=True, l=True) and cmds.optionMenuGrp(self.id, ex=True):
					cmds.optionMenuGrp(self.id, e=True, v=self.value)
					return
			cmds.optionMenuGrp(self.id, e=True, sl=1)
			self.updateVar()


	def updateVar(self):
		if self.id and cmds.optionMenuGrp(self.id, ex=True):
			cmds.optionVar(sv=[ self.getVarName(), cmds.optionMenuGrp(self.id, q=True, v=True) ])


	def getValueSub(self):
		try:
			'"'+self.value+'"'
		except:
			self.setupVar(True)
		return ( self.getName(), '"'+self.value+'"' )


class checkboxOption(option):

	__listCallback = None


	def __init__(self, parent, name, default, listCallback, share=False, short=None, positional=False):
		option.__init__(self, parent, name, default, share=share, short=short, positional=positional)
		self.__listCallback = listCallback
		if not isinstance(self.value, types.ListType):
			self.setupVar(True)


	def setupVarSub(self, pair):
		(name, value) = pair
		if value == 0:
			value = []
			cmds.optionVar(rm=name)
			cmds.optionVar(sva=[name,""])
		cmds.optionVar(ca=name)
		[ cmds.optionVar(sva=[name, v]) for v in value ]


	def showUI(self, layout):
		list = self.__listCallback
		if callable(self.__listCallback):
			list = self.__listCallback()

		if not isinstance(self.value, types.ListType):
			self.setupVar(True)

		if isinstance(list, types.ListType) and len(list) > 0:
			self.id = []
			i = list[0]
			self.id.append(cmds.checkBoxGrp(l=self.getDisplayName(), p=layout, ncb=1, l1=i, en1=True, v1=(i in self.value)))
			for i in list[1:]:
				self.id.append(cmds.checkBoxGrp(p=layout, ncb=1, l1=i, en1=True, v1=(i in self.value)))


	def updateUISub(self):
		if not isinstance(self.value, types.ListType):
			self.setupVar(True)

		for i in self.id:
			if cmds.checkBoxGrp(i, ex=True):
				v = cmds.checkBoxGrp(i, q=True, l1=True)
				cmds.checkBoxGrp(i, e=True, v1=(v in self.value))


	def updateVar(self):
		if not self.id:
			return
		def f(x): return not cmds.checkBoxGrp(x, ex=True)
		if not filter(f, self.id):	# update var only if all checkboxes exist
			name = self.getVarName()
			cmds.optionVar(ca=name)
			for i in self.id:
				if cmds.checkBoxGrp(i, q=True, v1=True):
					cmds.optionVar(sva=[ name, cmds.checkBoxGrp(i, q=True, l1=True) ])


	def getValueSub(self):
		if not isinstance(self.value, types.ListType):
			self.setupVar(True)
		return ( self.getName(), self.value )


class radioButtonOption(option):

	__listCallback = None


	def __init__(self, parent, name, default, listCallback, share=False, short=None, positional=False):
		option.__init__(self, parent, name, default, share=share, short=short, positional=positional)
		self.__listCallback = listCallback
		self.id = []
		try:
			self.value = str(self.value)
		except:
			self.setupVar(True)


	def setupVarSub(self, pair):
		cmds.optionVar(sv=pair)


	def showUI(self, layout):
		list = self.__listCallback
		if callable(self.__listCallback):
			list = self.__listCallback()
		if isinstance(list, types.ListType) and len(list) > 0:
			id = cmds.radioButtonGrp(p=layout, l=self.getDisplayName(), nrb=1, l1=list[0])
			self.id = []
			self.id.append((id, list[0]))
			for i in list[1:]:
				self.id.append((cmds.radioButtonGrp(p=layout, l="", nrb=1, scl=id, l1=i), i))


	def updateUISub(self):
		def f(x): return x[1]
		if self.value not in map(f, self.id):
			self.setupVar(True)
		for id,i in self.id:
			if i == self.value and cmds.radioButtonGrp(id, ex=True):
				cmds.radioButtonGrp(id, e=True, sl=True)
				return


	def updateVar(self):
		for id,i in self.id:
			if cmds.radioButtonGrp(id, ex=True) and cmds.radioButtonGrp(id, q=True, sl=True):
				cmds.optionVar(sv=[ self.getVarName(), i ])


	def getValueSub(self):
		try:
			'"'+self.value+'"'
		except:
			self.setupVar(True)
		return ( self.getName(), '"'+self.value+'"' )

############################## Start of Menu Builder ###########################

class	child:
	id = ""
	parent = None
	moduleName = ""	# this is to get access to activation code only
	
	def	__init__(self, moduleName, id, parent):
		self.moduleName = moduleName
		self.parent = parent
		self.id = id


class	mother(child):
	__prefix = ""
	__childInstanceMethod = None
	__list = []
	__serial = 0
	tx = ""

	def	__init__(self, moduleName, id, parent, prefix, method):
		child.__init__(self, moduleName, id, parent)
		self.__prefix = prefix
		self.__childInstanceMethod = method
		self.__serial = 0
		self.__list = []
		self.tx = ""

	def	add(self, id=None):
		if id and self.get(id):
			raise Exception, "item already exists"
		if not id:
			id = self.__prefix+str(self.__serial)
			self.__serial += 1
			while self.get(id):
				id = self.__prefix+str(self.__serial)
				self.__serial += 1
		element = self.__childInstanceMethod(self.moduleName, id, self)
		self.__list.append(element)
		return element

	def	get(self, id):
		def f(x): return x.id == id
		l = filter(f, self.__list)
		if l:
			return l[0]
		return None

	def	delete(self, id):
		l = self.get(id)
		if l:
			self.__list.remove(l)

	def	up(self, id, step=1):
		l = self.get(id)
		i = self.__list.index(l)
		self.__list.pop(i)
		n = len(self.__list)
		i = i-step
		if i < 0:
			i = i + n + 1
		self.__list.insert(i, l)

	def	down(self, id, step=1):
		l = self.get(id)
		i = self.__list.index(l)
		self.__list.pop(i)
		n = len(self.__list)
		i = i+step
		if i > n:
			i = i - n - 1
		self.__list.insert(i, l)

	def	first(self, id):
		l = self.get(id)
		i = self.__list.index(l)
		self.__list.pop(i)
		self.__list.insert(0, l)

	def	last(self, id):
		l = self.get(id)
		i = self.__list.index(l)
		self.__list.pop(i)
		self.__list.append(l)

	def	getList(self):
		return self.__list

	def	setFocus(self):
		cmds.setFocus(self.tx)


class	stringClass(child):
	strings = None
	collapse = "False"
	frame = ""

	def	__init__(self, moduleName, name, parent):
		child.__init__(self, moduleName, name, parent)
		self.strings = { "name":name }
		self.collapse = "False"
		self.frame = ""


class	optionClass(mother):
	strings = None
	positional = "True"
	type = ""
	collapse = "False"
	frame = ""
	defaultField = ""
	
	def	__init__(self, moduleName, name, parent):
		mother.__init__(self, moduleName, name, parent, "Value ", stringClass)
		self.strings = { "name":name, "short":"", "default":"" }
		self.positional = "True"
		self.type = ""
		self.collapse = "False"
		self.frame = ""
		self.defaultField = ""


	def	add(self, name=""):
		value = mother.add(self)
		value.strings['name'] = name


	def	delete(self, id):
		if len(mother.getList(self)) > 1:
			mother.delete(self, id)


	def	validateDefault(self):
		if self.type == 'int':
			try:
				int(self.strings["default"])
			except:
				self.strings["default"] = "0"
		elif self.type == 'float':
			try:
				float(self.strings["default"])
			except:
				self.strings["default"] = "0.0"
		elif self.type == 'bool':
			if isinstance(self.strings["default"], int):
				self.strings["default"] = str(self.strings["default"] != 0)
			elif isinstance(self.strings["default"], str) or isinstance(self.strings["default"], unicode):
				self.strings["default"] = str(self.strings["default"].lower() != "false" and self.strings["default"] != "0")
			else:
				self.strings["default"] = "True"
		elif self.type in ['list', 'radio', 'checkbox']:
			def f(x): return x.strings['name']
			l = map(f, self.getList())
			if self.strings["default"] not in l:
				if len(l) > 0:
					self.strings["default"] = l[0]
				else:
					self.strings["default"] = ''
		if cmds.textField(self.defaultField, q=True, ex=True):
			cmds.textField(self.defaultField, e=True, tx=self.strings["default"])


def	optionTypes():
	return [ "int", "float", "bool", "str", "list", "radio", "checkbox" ]


class	menuItemClass(mother):
	strings = None
	type = ""
	menu = None
	echo = "True"
	collapse = "False"
	frame = ""

	def	__init__(self, moduleName, name, parent):
		mother.__init__(self, moduleName, name, parent, "Option ", optionClass)
		self.menu = None
		self.echo = "True"
		self.strings = { "name":name, "command":"", "annotation":"" }
		self.collapse = "False"
		self.frame = ""

	def	add(self, name="", short='', default='', positional="False", type='int'):
		option = mother.add(self)
		option.strings["name"] = name
		option.strings["default"] = default
		option.positional = positional
		option.type = type
		option.strings["short"] = short
		return option

	def	initOptions(self):
		if self.type == 'submenu':
			self.menu.initOptions()
		elif self.type in [ 'mel', 'python' ]:
			options = self.getList()
			for option in options:
				s = option.strings['name'].replace(' ','')
				v = self.strings['command']+'.'+s[0].lower()+s[1:]
				if cmds.optionVar(ex=v):
					cmds.optionVar(rm=v)

	def	newMenu(self):
		self.menu = menuClass(self.moduleName, self.id, self)
		self.menu.strings['name'] = self.strings['name']
		return self.menu


def	menuItemTypes():
	return [ "mel", "python", "divider", "submenu" ]


class	menuClass(mother):
	dependencies = None
	extraPaths = None
	strings = None
	autoload = "True"
	initOpt = "True"
	__gShelfTopLevel = ""


	def	__init__(self, moduleName, menuId, parent=""):
		mother.__init__(self, moduleName, menuId, parent, "Menu Item ", menuItemClass)
		self.dependencies = { 'mel':[], 'python':[], 'plugin':[] }
		self.extraPaths = { 'mel':[], 'python':[], 'plugin':[] }
		self.strings = { "name":'' }
		self.getAutoload()
		self.initOpt = "True"
		self.__gShelfTopLevel = mel.eval("$tempVar=$gShelfTopLevel")


	def	getEnvPaths(self, typ):
		paths = []
		env = { "mel":"MAYA_SCRIPT_PATH", "python":"PYTHONPATH", "plugin":"MAYA_PLUG_IN_PATH" }
		if env[typ] in os.environ:
			paths += os.environ[env[typ]].split(';')
		empty = paths.count('')
		for i in range(empty):
			paths.remove('')
		paths = map(os.path.abspath, paths)
		def f(x): return x.replace('\\','/')
		return map(f, paths)


	def	splitPath(self, type, path):
		if type == "python":
			module = os.path.basename(path).replace('.pyc','').replace('.py','')
			d = os.path.dirname(path)
			while len(d) > 3:	# this is the length of root directory, eg. "c:/"
				if os.path.isfile(os.path.join(d, "__init__.py")) or os.path.isfile(os.path.join(d, "__init__.pyc")):
					module = os.path.basename(d) + '.' + module
					d = os.path.dirname(d)
				else:
					break
			return ( d.replace('\\','/'), module )
		else:
			return ( os.path.dirname(path).replace('\\','/'), os.path.basename(path) )


	def	pathInList(self, path, paths):
		def l(x): return x.lower()
		if cmds.about(nt=True):
			return path.lower() in map(l, paths)
		return path in paths


	def	updateDependencies(self, type, path):
		# to be called by add and parseCSV

		if not path:
			return None
		path = path.replace('\\','/')
		if path.endswith('.mll'):
			type = 'plugin'

		if 'path' in type:
			if not self.pathInList(path, self.extraPaths[type[:-4]]):
				self.extraPaths[type[:-4]].append(path)
		elif '/' in path:
			dir, file = self.splitPath(type, path)
			if self.pathInList(dir, self.getEnvPaths(type)):
				if file not in self.dependencies[type]:
					self.dependencies[type].append(file)
				return ( '', file )
			else:
				if not self.pathInList(dir, self.extraPaths[type]):
					self.extraPaths[type].append(dir)
				if file not in self.dependencies[type]:
					self.dependencies[type].append(file)
				return ( dir, file )
		else:
			if path not in self.dependencies[type]:
				self.dependencies[type].append(path)


	def	add(self, name='', command='', type='mel', echo='True', depend='', annotation=''):
		item = mother.add(self)
		item.strings["name"] = name
		item.strings["command"] = command
		item.type = type
		item.echo = echo
		item.strings["annotation"] = annotation
		if depend:
			self.updateDependencies(type, depend)
		return item


	def	open(self, menuId=None):
		if not menuId:
			menuId = self.id
		self.id = menuId
		self.getAutoload()
		currentTab = cmds.tabLayout(self.__gShelfTopLevel, q=True, st=True)
		previousTab = currentTab
		if cmds.optionVar(ex=self.moduleName+".selectShelf.shelf"):
			currentTab = cmds.optionVar(q=self.moduleName+".selectShelf.shelf")
			if currentTab in cmds.tabLayout(self.__gShelfTopLevel, q=True, ca=True):
				cmds.tabLayout(self.__gShelfTopLevel, e=True, st=currentTab)
			else:
				currentTab = previousTab
		cmds.setParent(currentTab)
		if cmds.shelfLayout(currentTab, q=True, ca=True):
			for b in cmds.shelfLayout(currentTab, q=True, ca=True):
				if cmds.shelfButton(b, q=True, ex=True):
					if menuId == cmds.shelfButton(b, q=True, l=True):
						class menuCSV:
							buffer = None
							i = -1
							def __init__(self, content):
								self.i = -1
								def f(x): return x.startswith("#")
								content = content.replace("\n", "\r")
								self.buffer = filter(f, content.strip().split("\r"))
							def __iter__(self):
								return self
							def next(self):
								self.i += 1
								if self.i >= len(self.buffer):
									raise StopIteration
								return self.buffer[self.i]
						self.parseCSV(menuCSV(cmds.shelfButton(b, q=True, c=True)))
		cmds.tabLayout(self.__gShelfTopLevel, e=True, st=previousTab)


	def	build(self, menuId=None):
		self.open(menuId)
		exec(self.generateScript())


	def	setAutoload(self):
		if cmds.optionVar(ex=self.moduleName+".autoload.menus"):
			mns = cmds.optionVar(q=self.moduleName+".autoload.menus")
			if self.autoload == "True" and self.id not in mns:
				cmds.optionVar(sva=[self.moduleName+".autoload.menus", self.id])
			elif self.autoload != "True" and self.id in mns:
				cmds.optionVar(rfa=[self.moduleName+".autoload.menus", mns.index(self.id)])
		elif self.autoload == "True":
			cmds.optionVar(sva=[self.moduleName+".autoload.menus", self.id])

	def	getAutoload(self):
		self.autoload = "True"
		if cmds.optionVar(ex=self.moduleName+".autoload.menus"):
			mns = cmds.optionVar(q=self.moduleName+".autoload.menus")
			if self.id not in mns:
				self.autoload = "False"
		else:
			cmds.optionVar(sva=[self.moduleName+".autoload.menus", self.id])


	def	initOptions(self):
		[ child.initOptions() for child in self.getList() ]


	def	generateScript(self, level=0):
		try:
			if cmds.optionVar(ex=self.moduleName+".activationCode"):
				acode = cmds.optionVar(q=self.moduleName+".activationCode")
				if acode.replace('-','').lower() != bx():
					raise Exception
			else:
				raise Exception
		except:
			sys.exit("activation error")

		if not self.getList():
			return ""

		for typ in [ 'mel', 'python', 'plugin' ]:
			loadFiles(typ, self.dependencies[typ], self.extraPaths[typ])

		script = ""
		if level == 0:
			script  = "import maya.cmds as cmds\nimport maya.mel as mel\n"
			script += "destroyMenu('"+self.id+"')\n"
			if isinstance(self.parent, types.StringType) or isinstance(self.parent, types.UnicodeType):
				script += "m"+str(level)+" = createMenu('"+self.id+"', '"+self.parent+"')\n"
			else:
				script += "m"+str(level)+" = createMenu('"+self.id+"')\n"

		itemMethods = { "mel":"melItem", "python":"commandItem" }
		optionMethods = { "int": "integerOption",	\
			"float": "floatOption",	\
			"bool": "booleanOption",	\
			"str": "stringOption",		\
			"list": "listOption",	\
			"radio": "radioButtonOption",	\
			"checkbox": "checkboxOption" }
		for l in self.getList():
			if l.type == 'mel' or l.type == 'python':
				script += "i = "+itemMethods[l.type]+"(m"+str(level)+", '"+l.strings["command"]+"', '"+l.strings["name"]+"', "+l.echo+", '"+l.strings["annotation"]+"')\n"
				for o in l.getList():
					o.validateDefault()
					script += optionMethods[o.type]+"(i, '"+o.strings["name"][0].lower()+o.strings["name"][1:]+"', "

					# default value
					if o.strings["default"]:
						if o.type in [ "str", "list", "radio" ]:
							script += "'"+o.strings["default"]+"'"
						elif o.type == "checkbox":
							script += "["
							# default value of a checkbox option is comma or semi-colon delimited
							for v in o.strings["default"].replace(',',';').split(';'):
								script += "'"+v+"',"
							script = script.strip(',')
							script += "]"
						else:
							script += o.strings["default"]
					else:
						if o.type in [ "str", "list", "radio" ]:
							script += "''"
						elif o.type == "checkbox":
							script += "[]"
						elif o.type == "bool":
							script += "True"
						else:
							script += "0"

					# value list
					if o.type in [ "list", "radio", "checkbox" ]:
						script += ", ["
						for v in o.getList():
							script += "'"+v.strings["name"]+"',"
						script.rstrip(",")
						script = script.strip(',')
						script += "] "

					# short name
					if o.strings["short"]:
						script += ", short='" + o.strings["short"] + "'"

					script += ", positional=" + o.positional

					script += ")\n"
			elif l.type == 'divider':
				script += "dividerItem(m"+str(level)+")\n"
			elif l.type == 'submenu':
				script += "m"+str(level+1)+" = subMenuItem(m"+str(level)+", '"+l.strings["name"]+"')\n"
				script += l.menu.generateScript(level+1)

		if level == 0:
			script += "dividerItem(m0)\n"
			script += "commandItem(m0, '"+self.moduleName+".destroyMenu(\\'"+self.id+"\\')', 'Dismiss')\n"
		return script


	def	parseCSV(self, fileObj):
		bool = re.compile("y|true|1", re.I)
		reader = csv.reader(fileObj)
		def parse(menu, row, reader, level):
			itm = None
			currentItm = ""
			currentOpt = ""
			while True:
				if not row:
					return
				if row[0].lower() == "#menu" and len(row) > 2:
					menu.strings["name"] = row[1]
					currentLvl = int(row[2])
					if not menu.parent and len(row) > 3 and row[3]:
						menu.parent = row[3]
					if currentLvl > level and itm and itm.type == 'submenu':
						row = parse(itm.newMenu(), reader.next(), reader, currentLvl)
						continue
				elif row[0].lower().startswith("#menuitem") and len(row) == 7:
					if int(row[6]) < level:
						return row
					itm = menu.add(name=row[1], command=row[2], type=row[3], echo=row[4], annotation=row[5])
					currentItm = itm.id
				elif row[0].lower().startswith("#option") and len(row) == 6:
					itm = menu.get(currentItm)
					if itm:
						opt = itm.add(name=row[1], short=row[2], default=row[3], positional=row[4], type=row[5])
						currentOpt = opt.id
				elif row[0].lower().startswith("#value") and len(row) == 2:
					itm = menu.get(currentItm)
					opt = itm.get(currentOpt)
					opt.add(name=row[1])
				elif row[0].lower() in [ "#mel", "#python", "#plugin", "#melpath", "#pythonpath", "#pluginpath" ] and len(row) == 3 and row[1]:
					if int(row[2]) < level:
						return row
					menu.updateDependencies(row[0].lower().strip('#'), row[1])
				try:
					row = reader.next()
				except:
					return
		try:
			parse(self, reader.next(), reader, 0)
		except csv.Error, e:
		    raise Exception, 'line %d: %s' % (reader.line_num, e)


	def	generateCSV(self, fileObj, level=0):
		def concatenate(x,y): return x+" "+y
		writer = csv.writer(fileObj)
		row = [ "#Menu", self.strings["name"], level ]
		if isinstance(self.parent, types.StringType) or isinstance(self.parent, types.UnicodeType):
			# condition for root menu, submenu's parent would not be of string type
			row.append(self.parent)
		writer.writerow(row)
		for l in self.getList():
			row = [ "#MenuItem", l.strings["name"], l.strings["command"], l.type, l.echo, l.strings["annotation"], level ]
			writer.writerow(row)
			if l.type == 'submenu':
				l.menu.generateCSV(fileObj, level+1)
			elif l.type == 'mel' or l.type == 'python':
				for o in l.getList():
					o.validateDefault()
					row = [ "#Option", o.strings["name"], o.strings["short"], o.strings["default"], o.positional, o.type ]
					writer.writerow(row)
					if o.type in [ 'list', 'radio', 'checkbox' ]:
						for v in o.getList():
							row = [ "#Value", v.strings["name"] ]
							writer.writerow(row)
		for typ in [ 'mel', 'python', 'plugin' ]:
			for file in self.dependencies[typ]:
				row = [ "#"+typ.capitalize(), file, level ]
				writer.writerow(row)
			for dir in self.extraPaths[typ]:
				row = [ "#%s%s" % (typ.capitalize(), 'path'), dir, level ]
				writer.writerow(row)


class	menuBuilderClass:

	__moduleName = ""
	__window = ""
	__gShelfTopLevel = ""
	__menu = None
	__rootMenu = None
	__backButton = ""
	__menuCmds = None
	__pane = "menu"
	__item = None
	__paneLayout = ""
	__panes = None


	def	__init__(self, moduleName):
		self.__moduleName = moduleName
		self.__window = self.__moduleName.replace('.','_')+"_menuBuilderWindow"
		self.__gShelfTopLevel = mel.eval("$tempVar=$gShelfTopLevel")
		self.__menu = None
		self.__rootMenu = None
		self.__backButton = ""
		self.__menuCmds = { "file":"", "item":[] }
		self.__pane = "menu"	# other values: "mel", "python", "plugin"
		self.__item = None
		self.__paneLayout = ""
		self.__panes = []


	def	__changeContext(self, context, contextType):
		s = "Menu Builder - %s (%s)" % (context, contextType.capitalize())
		cmds.window(self.__window, e=True, t=s)


	def	__enablePanes(self, enable):
		for p in self.__panes:
			try:
				exec("cmds."+cmds.objectTypeUI(p)+"(p, e=True, en=enable)")
			except:
				exec("cmds.menuItem(p, e=True, en=enable)")


	def	showWindow(self, menuId=None):
		if cmds.window(self.__window, q=True, ex=True):
			cmds.showWindow(self.__window)
			return

		self.loadShelf(menuId)

		totalWidth = 380
		w = cmds.window(self.__window, t="Menu Builder", w=totalWidth, h=630, mb=True)
		fl = cmds.formLayout()

		size=30
		rl = cmds.rowLayout(nc=8)
		cmds.rowLayout(rl, e=True, cw=[1, size])
		cmds.rowLayout(rl, e=True, cw=[2, size])
		cmds.rowLayout(rl, e=True, cw=[3, size])
		cmds.rowLayout(rl, e=True, cw=[4, size])
		cmds.rowLayout(rl, e=True, cw=[5, size+20])
		cmds.rowLayout(rl, e=True, cw=[6, size])
		cmds.rowLayout(rl, e=True, cw=[7, size])
		cmds.rowLayout(rl, e=True, cw=[8, size])
		cmds.rowLayout(rl, e=True, cat=[1, "right", 0])
		cmds.rowLayout(rl, e=True, cat=[2, "right", 0])
		cmds.rowLayout(rl, e=True, cat=[3, "right", 0])
		cmds.rowLayout(rl, e=True, cat=[4, "right", 0])
		cmds.rowLayout(rl, e=True, cat=[5, "right", 0])
		cmds.rowLayout(rl, e=True, cat=[6, "right", 0])
		cmds.rowLayout(rl, e=True, cat=[7, "right", 0])
		cmds.rowLayout(rl, e=True, cat=[8, "right", 0])
		icons = { 
			'2008': ['insert.xpm', 'mayaIcon.xpm', 'kinhandle.xpm', 'newLayerEmpty.xpm', 'smallTrash.xpm', 'arrowUp.xpm', 'arrowDown.xpm' ],
			'2009': ['insert.xpm', 'mayaIcon.xpm', 'kinhandle.xpm', 'newLayerEmpty.xpm', 'smallTrash.xpm', 'arrowUp.xpm', 'arrowDown.xpm' ],
			'2010': ['insert.xpm', 'mayaIcon.xpm', 'kinhandle.xpm', 'newLayerEmpty.xpm', 'smallTrash.xpm', 'arrowUp.xpm', 'arrowDown.xpm' ],
			'2011': ['insert.png', 'factoryIcon.png', 'kinhandle.png', 'newLayerEmpty.png', 'smallTrash.png', 'moveLayerUp.png', 'moveLayerDown.png' ],
			'2012': ['insert.png', 'factoryIcon.png', 'kinhandle.png', 'newLayerEmpty.png', 'smallTrash.png', 'moveLayerUp.png', 'moveLayerDown.png' ]
				}
		version = cmds.about(v=True)[:4]
		cmds.symbolButton(image=icons[version][0], w=size, h=size, c=self.__moduleName+".menuBuilderCallback(method='showMenu')")
		self.__panes = []
		self.__panes.append(cmds.symbolButton(image=icons[version][1], w=size, h=size, c=self.__moduleName+".menuBuilderCallback(method='showDependencies', dependType='mel')"))
		self.__panes.append(cmds.iconTextButton(st='textOnly', w=size, h=size, l='Py', fn="boldLabelFont", c=self.__moduleName+".menuBuilderCallback(method='showDependencies', dependType='python')"))
		self.__panes.append(cmds.symbolButton(image=icons[version][2], w=size, h=size, c=self.__moduleName+".menuBuilderCallback(method='showDependencies', dependType='plugin')"))
		cmds.symbolButton(image=icons[version][3], w=size, h=size, c=self.__moduleName+".menuBuilderCallback(method='action', action='add')")
		cmds.symbolButton(image=icons[version][4], w=size, h=size, c=self.__moduleName+".menuBuilderCallback(method='action', action='delete')")
		cmds.symbolButton(image=icons[version][5], w=size, h=size, c=self.__moduleName+".menuBuilderCallback(method='action', action='up', step=1)")
		cmds.symbolButton(image=icons[version][6], w=size, h=size, c=self.__moduleName+".menuBuilderCallback(method='action', action='down', step=1)")

		cmds.setParent('..')
		self.__paneLayout = cmds.formLayout(p=fl)
		cmds.formLayout(fl, e=True, af=[(rl, 'top', 0), (rl, 'right', 0), (rl, 'left', 0)], an=[(rl, 'bottom')])
		cmds.formLayout(fl, e=True, af=[(self.__paneLayout, 'bottom', 0), (self.__paneLayout, 'right', 0), (self.__paneLayout, 'left', 0)], ac=[(self.__paneLayout, 'top', 0, rl)])
		self.showMenu()

		destroyMenu(self.__window+"|File")
		m = createMenu(self.__window+"|File", w)
		self.__menuCmds['file'] = m.getId()
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='loadMenu')", "Load Menu")
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='saveMenu')", "Save Menu")
		dividerItem(m)
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='importFiles')", "Import Files")

		destroyMenu(self.__window+"|Pane")
		m = createMenu(self.__window+"|Pane", w)
		commandItem(m, self.__moduleName+".menuBuilderCallback(method='showMenu')", "Menu")
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='showDependencies', dependType='mel')", "MEL")
		self.__panes.append(c.getId())
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='showDependencies', dependType='python')", "Python")
		self.__panes.append(c.getId())
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='showDependencies', dependType='plugin')", "Plug-ins")
		self.__panes.append(c.getId())

		destroyMenu(self.__window+"|Item")
		m = createMenu(self.__window+"|Item", w)
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='action', action='add')", "Add")
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='action', action='delete')", "Delete")
		dividerItem(m)
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='action', action='up', step=1)", "Up")
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='action', action='down', step=1)", "Down")
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='action', action='first', step=0)", "First")
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='action', action='last', step=0)", "Last")
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='action', action='up', step=10)", "Up More")
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='action', action='down', step=10)", "Down More")
		dividerItem(m)
		self.__menuCmds['item'] = []
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='collapseFrame', collapse='True', item='all')", "Collapse All")
		self.__menuCmds['item'].append(c.getId())
		c = commandItem(m, self.__moduleName+".menuBuilderCallback(method='collapseFrame', collapse='False', item='all')", "Expand All")
		self.__menuCmds['item'].append(c.getId())

		cmds.showWindow(self.__window)


	def	showMenu(self):
		ca = cmds.layout(self.__paneLayout, q=True, ca=True)
		if ca: [ cmds.deleteUI(x) for x in ca ]

		cmds.setParent(self.__paneLayout)
		buttomForm = cmds.formLayout()
		b1 = cmds.button(l="Save", w=60)
		cmds.formLayout(buttomForm, e=True, af=[(b1, "top", 10), (b1, "bottom", 5), (b1, "right", 10)], an=[(b1, "left")])
		self.__backButton = b1

		itemForm = cmds.formLayout(p=self.__paneLayout)
		sl = cmds.scrollLayout(p=itemForm, cr=True)
		self.show(sl)
		cmds.formLayout(itemForm, e=True, af=[(sl, "top", 0), (sl, "left", 0), (sl, "right" ,0), (sl, "bottom" ,0)])

		cmds.formLayout(self.__paneLayout, e=True, af=[(buttomForm, "top", 0), (buttomForm, "left", 0), (buttomForm, "right", 0)], an=[(buttomForm, "bottom")])
		cmds.formLayout(self.__paneLayout, e=True, ac=[(itemForm, "top", 0, buttomForm)], af=[(itemForm, "left", 0), (itemForm, "right", 0), (itemForm, "bottom", 0)])

		cmds.button(b1, e=True, c=self.__moduleName+".menuBuilderCallback(method='back', layout='"+sl+"')")

		if self.__menu.parent and not isinstance(self.__menu.parent, types.StringType) and not isinstance(self.__menu.parent, types.UnicodeType):
			cmds.button(b1, e=True, l="Back")

		self.__changeMenuCmdsState(True)
		
		self.__pane = "menu"


	def	show(self, layout):
		ctxType = "Menu"
		if isinstance(self.__menu, menuClass) or (isinstance(self.__menu, menuItemClass) and self.__menu.type == "submenu"):
			self.showItems(layout)
			if not isinstance(self.__menu.parent, types.StringType) and not isinstance(self.__menu.parent, types.UnicodeType):
				ctxType = "Submenu"
			self.__enablePanes(True)
		elif isinstance(self.__menu, menuItemClass) and (self.__menu.type == "mel" or self.__menu.type == "python"):
			self.showOptions(layout)
			ctxType = "Command"
			self.__enablePanes(False)
		elif isinstance(self.__menu, optionClass):
			self.showValues(layout)
			ctxType = "Option"
			self.__enablePanes(False)
		else:
			raise Exception, "unknown menu instance"
		self.__pane = "menu"
		if self.__menu.strings['name']:
			self.__changeContext(self.__menu.strings['name'], ctxType)
		else:
			self.__changeContext(self.__menu.id, ctxType)


	def	__changeMenuCmdsState(self, state):
		if cmds.menu(self.__menuCmds['file'], q=True, ex=True):
			cmds.menu(self.__menuCmds['file'], e=True, en=state)
		for i in self.__menuCmds['item']:
			if cmds.menuItem(i, q=True, ex=True):
				cmds.menuItem(i, e=True, en=state)


	def	showDependencies(self, dependType):
		ca = cmds.layout(self.__paneLayout, q=True, ca=True)
		if ca: [ cmds.deleteUI(x) for x in ca ]

		self.__pane = dependType
		cmds.setParent(self.__paneLayout)

		tsl = ""
		tsl2 = ""
		txlabel = { 'mel':'MEL files', 'python':'Python modules', 'plugin':'Plug-ins' }
		bnlabel = { 'mel':'Source', 'python':'Import', 'plugin':'Load' }
		menu = None
		if isinstance(self.__menu, menuClass):
			menu = self.__menu
		elif isinstance(self.__menu, menuItemClass) and self.__menu.type == "submenu":
			menu = self.__menu.menu

		t = cmds.text(l=txlabel[dependType], al="left")
		b = cmds.button(l=bnlabel[dependType], w=60, en=menu!=None)
		tsl = cmds.textScrollList(ams=True, en=menu!=None)
		if menu:
			[ cmds.textScrollList(tsl, e=True, a=x) for x in menu.dependencies[dependType] ]
			pm = cmds.popupMenu()
			cmds.popupMenu(pm, e=True, pmc=self.__moduleName+".menuBuilderCallback(method='action', action='browse', popupMenu='"+pm+"')")

		cmds.setParent(self.__paneLayout)
		t2 = cmds.text(l="Extra paths", al="left")
		tsl2 = cmds.textScrollList(nr=5, ams=True, en=menu!=None)
		if menu:
			[ cmds.textScrollList(tsl2, e=True, a=x) for x in menu.extraPaths[dependType] ]

		cmds.formLayout(self.__paneLayout, e=True, af=[(tsl2, "left", 10), (tsl2, "right", 10), (tsl2, "bottom", 10)], an=[(tsl2, "top")])
		cmds.formLayout(self.__paneLayout, e=True, ac=[(t2, "bottom", 5, tsl2)], af=[(t2, "left", 10)], an=[(t2, "right"), (t2, "top")])
		cmds.formLayout(self.__paneLayout, e=True, af=[(t, "left", 10), (t, "right", 10), (t, "top", 10)], an=[(t, "bottom")])
		cmds.formLayout(self.__paneLayout, e=True, af=[(b, "top", 10), (b, "right", 10)], an=[(b, "left"), (b, "bottom")])
		cmds.formLayout(self.__paneLayout, e=True, af=[(tsl, "left", 10), (tsl, "right", 10)], ac=[(tsl, "top", 5, b), (tsl, "bottom", 5, t2)])

		cmds.textScrollList(tsl, e=True, dkc=self.__moduleName+".menuBuilderCallback(method='action', action='delete')")
		cmds.textScrollList(tsl2, e=True, dkc=self.__moduleName+".menuBuilderCallback(method='action', action='delete')")

		cmds.textScrollList(tsl, e=True, dcc=self.__moduleName+".menuBuilderCallback(method='action', action='test')")

		cmds.button(b, e=True, c=self.__moduleName+".menuBuilderCallback(method='action', action='test')")

		self.__changeMenuCmdsState(False)


	def	showItems(self, layout):
		cmds.setParent(layout)
		if cmds.columnLayout("itemList", q=True, ex=True):
			cmds.deleteUI("itemList")

		pl = cmds.columnLayout("itemList", adj=True)

		for p in self.__menu.getList():
			fr = cmds.frameLayout(p=pl, cll=True, l=p.strings["name"], cl=p.collapse=="True", w=350)
			cmds.frameLayout(fr, e=True, cc=self.__moduleName+".menuBuilderCallback(method='collapseFrame', collapse='True', item='"+p.id+"')")
			cmds.frameLayout(fr, e=True, ec=self.__moduleName+".menuBuilderCallback(method='collapseFrame', collapse='False', item='"+p.id+"')")
			p.frame = fr

			fl = cmds.formLayout(p=fr)
			cl = cmds.columnLayout(adj=True)
			cmds.formLayout(fl, e=True, af=[(cl, "top", 0), (cl, "bottom", 0), (cl, "left", 0), (cl, "right", 0)])

			firstColWidth = 60
			secondColWidth = 215
			thirdColWidth = 60

			fl = cmds.formLayout(p=cl, h=30)
			t1 = cmds.text(l="Name:", w=firstColWidth, al="left")
			tf1 = cmds.textField(tx=p.strings["name"], w=secondColWidth)
			b1 = cmds.button(l="Options", w=thirdColWidth, c=self.__moduleName+".menuBuilderCallback(method='options', item='"+p.id+"', layout='"+layout+"')")
			cmds.formLayout(fl, e=True, af=[(t1, "top", 9), (t1, "left", 5)], an=[(t1, "bottom"), (t1, "right")])
			cmds.formLayout(fl, e=True, af=[(b1, "top", 7), (b1, "right", 25)], an=[(b1, "bottom"), (b1, "left")])
			cmds.formLayout(fl, e=True, af=[(tf1, "top", 7)], ac=[(tf1, "left", 0, t1), (tf1, "right", 5, b1)], an=[(tf1, "bottom")])

			fl = cmds.formLayout(p=cl, h=30)
			t2 = cmds.text(l="Command:", w=firstColWidth, al="left")
			tf2 = cmds.textField(tx=p.strings["command"], w=secondColWidth)
			cb2 = cmds.checkBox(l="Echo", v=p.echo=="True", w=thirdColWidth)
			cmds.formLayout(fl, e=True, af=[(t2, "top", 9), (t2, "left", 5)], an=[(t2, "bottom"), (t2, "right")])
			cmds.formLayout(fl, e=True, af=[(cb2, "top", 7), (cb2, "right", 25)], an=[(cb2, "bottom"), (cb2, "left")])
			cmds.formLayout(fl, e=True, af=[(tf2, "top", 7)], ac=[(tf2, "left", 0, t2), (tf2, "right", 5, cb2)], an=[(tf2, "bottom")])

			fl = cmds.formLayout(p=cl)
			rb = cmds.radioButtonGrp("type", l="Type:", nrb=4, la4=menuItemTypes(), sl=menuItemTypes().index(p.type)+1, vr=False, cl5=["left","left","left","left","left"], ct5=["left","left","left","left","left"], co5=[0,0,0,0,0], h=25, cw5=[firstColWidth,35,53,53,47])
			cmds.radioButtonGrp(rb, e=True, rat=[2,"both",5])
			cmds.radioButtonGrp(rb, e=True, rat=[3,"both",5])
			cmds.radioButtonGrp(rb, e=True, rat=[4,"both",5])
			b3 = cmds.button(l="Submenu", w=thirdColWidth, c=self.__moduleName+".menuBuilderCallback(method='submenu', item='"+p.id+"', layout='"+layout+"')")
			cmds.formLayout(fl, e=True, af=[(rb, "top", 7), (rb, "left", 5)], an=[(rb, "bottom"), (rb, "right")])
			cmds.formLayout(fl, e=True, af=[(b3, "top", 7), (b3, "right", 25)], an=[(b3, "left"), (b3, "bottom")])

			fl = cmds.formLayout(p=cl, h=30)
			t3 = cmds.text(l="Annotation:", w=firstColWidth, al="left")
			tf3 = cmds.textField(tx=p.strings["annotation"], w=secondColWidth+thirdColWidth)
			cmds.formLayout(fl, e=True, af=[(t3, "top", 9), (t3, "left", 5)], an=[(t3, "bottom"), (t3, "right")])
			cmds.formLayout(fl, e=True, af=[(tf3, "top", 7), (tf3, "right", 25)], ac=[(tf3, "left", 0, t3)], an=[(tf3, "bottom")])

			cmds.textField(tf1, e=True, aie=True, ec="import maya.cmds\nmaya.cmds.setFocus('"+tf2+"')", cc=self.__moduleName+".menuBuilderCallback(method='changeText', item='"+p.id+"', textField='"+tf1+"', field='name', frameLayout='"+fr+"')")
			cmds.textField(tf1, e=True, rfc=self.__moduleName+".menuBuilderCallback(method='changeItem', item='"+p.id+"')")
			cmds.checkBox(cb2, e=True, cc=self.__moduleName+".menuBuilderCallback(method='changeCheckBox', item='"+p.id+"', checkBox='"+cb2+"')")
			cmds.textField(tf2, e=True, aie=True, ec="import maya.cmds\nmaya.cmds.setFocus('"+tf3+"')", cc=self.__moduleName+".menuBuilderCallback(method='changeText', item='"+p.id+"', textField='"+tf2+"', field='command')")
			cmds.textField(tf2, e=True, rfc=self.__moduleName+".menuBuilderCallback(method='changeItem', item='"+p.id+"')")
			cmds.radioButtonGrp(rb, e=True, cc=self.__moduleName+".menuBuilderCallback(method='changeRadio', item='"+p.id+"', radioButtonGrp='"+rb+"', nameField='"+tf1+"', commandField='"+tf2+"', optionsButton='"+b1+"', submenuButton='"+b3+"', echoCheckBox='"+cb2+"', annotationField='"+tf3+"')")
			cmds.textField(tf3, e=True, aie=True, ec="import maya.cmds\nmaya.cmds.setFocus('"+tf1+"')", cc=self.__moduleName+".menuBuilderCallback(method='changeText', item='"+p.id+"', textField='"+tf3+"', field='annotation')")
			cmds.textField(tf3, e=True, rfc=self.__moduleName+".menuBuilderCallback(method='changeItem', item='"+p.id+"')")

			selected = menuItemTypes().index(p.type)
			if selected == 0 or selected == 1:
				cmds.textField(tf1, e=True, en=True)
				cmds.textField(tf2, e=True, en=True)
				cmds.button(b1, e=True, en=True)
				cmds.button(b3, e=True, en=False)
				cmds.textField(tf3, e=True, en=True)
				cmds.checkBox(cb2, e=True, en=True)
			elif selected == 2:
				cmds.textField(tf1, e=True, en=False)
				cmds.textField(tf2, e=True, en=False)
				cmds.button(b1, e=True, en=False)
				cmds.button(b3, e=True, en=False)
				cmds.textField(tf3, e=True, en=False)
				cmds.checkBox(cb2, e=True, en=False)
			elif selected == 3:
				cmds.textField(tf1, e=True, en=True)
				cmds.textField(tf2, e=True, en=False)
				cmds.button(b1, e=True, en=False)
				cmds.button(b3, e=True, en=True)
				cmds.textField(tf3, e=True, en=False)
				cmds.checkBox(cb2, e=True, en=False)

			cmds.setFocus(tf1)
			p.tx = tf1


	def	showOptions(self, layout):
		cmds.setParent(layout)
		if cmds.columnLayout("itemList", q=True, ex=True):
			cmds.deleteUI("itemList")

		pl = cmds.columnLayout("itemList", adj=True)

		for p in self.__menu.getList():
			fr = cmds.frameLayout(p=pl, cll=True, l=p.strings["name"], cl=p.collapse=="True", w=350)
			cmds.frameLayout(fr, e=True, cc=self.__moduleName+".menuBuilderCallback(method='collapseFrame', collapse='True', item='"+p.id+"')")
			cmds.frameLayout(fr, e=True, ec=self.__moduleName+".menuBuilderCallback(method='collapseFrame', collapse='False', item='"+p.id+"')")
			p.frame = fr

			fl = cmds.formLayout(p=fr)
			cl = cmds.columnLayout(adj=True)
			cmds.formLayout(fl, e=True, af=[(cl, "top", 0), (cl, "bottom", 0), (cl, "left", 0), (cl, "right", 0)])

			firstColWidth = 60
			secondColWidth = 210
			thirdColWidth = 65

			fl = cmds.formLayout(p=cl, h=30)
			t1 = cmds.text(l="Name:", w=firstColWidth, al="left")
			tf1 = cmds.textField(tx=p.strings["name"], w=secondColWidth)
			cb1 = cmds.checkBox(l="Positional", v=p.positional=="True", w=thirdColWidth)
			cmds.formLayout(fl, e=True, af=[(t1, "top", 9), (t1, "left", 5)], an=[(t1, "bottom"), (t1, "right")])
			cmds.formLayout(fl, e=True, af=[(cb1, "top", 7), (cb1, "right", 25)], an=[(cb1, "left"), (cb1, "bottom")])
			cmds.formLayout(fl, e=True, af=[(tf1, "top", 7)], ac=[(tf1, "left", 0, t1), (tf1, "right", 5, cb1)], an=[(tf1, "bottom")])

			cmds.rowLayout(p=cl, h=30, nc=5, ad5=4, cw5=[firstColWidth, secondColWidth/3, 60, secondColWidth/3, thirdColWidth+25], ct5=["left","left","right","left","left"], co5=[5,0,5,0,0])
			t2 = cmds.text(l="Short:", al="left")
			tf2 = cmds.textField(tx=p.strings["short"])
			t3 = cmds.text(l="Default:", al="right")
			tf3 = cmds.textField(tx=p.strings["default"])
			t4 = cmds.text(l="", w=thirdColWidth+25)
			p.defaultField = tf3

			fl = cmds.formLayout(p=cl)
			rb1 = cmds.radioButtonGrp(l="Type:", nrb=4, la4=optionTypes()[:4], vr=False, cl5=["left","left","left","left","left"], ct5=["left","left","left","left","left"], co5=[0,0,0,0,0], h=25, cw5=[firstColWidth,40,50,50,40])
			cmds.radioButtonGrp(rb1, e=True, rat=[2,"both",5])
			cmds.radioButtonGrp(rb1, e=True, rat=[3,"both",5])
			cmds.radioButtonGrp(rb1, e=True, rat=[4,"both",5])
			rb2 = cmds.radioButtonGrp(l="", scl=rb1, nrb=3, la3=optionTypes()[4:], vr=False, cl4=["left","left","left","left"], ct4=["left","left","left","left"], co4=[0,0,0,0], h=25, cw4=[firstColWidth,40,50,60])
			cmds.radioButtonGrp(rb2, e=True, rat=[2,"both",5])
			cmds.radioButtonGrp(rb2, e=True, rat=[3,"both",5])
			b2 = cmds.button(l="Values", w=thirdColWidth, c=self.__moduleName+".menuBuilderCallback(method='values', item='"+p.id+"', layout='"+layout+"')")
			cmds.formLayout(fl, e=True, af=[(rb1, "top", 7), (rb1, "left", 5)], an=[(rb1, "bottom"), (rb1, "right")])
			cmds.formLayout(fl, e=True, af=[(rb2, "left", 5)], ac=[(rb2, "top", 7, rb1)], an=[(rb2, "bottom"), (rb2, "right")])
			cmds.formLayout(fl, e=True, ac=[(b2, "top", 7, rb1)], an=[(b2, "bottom"), (b2, "left")], af=[(b2, "right", 25)])
			sl = optionTypes().index(p.type)
			if sl < 4:
				cmds.radioButtonGrp(rb1, e=True, sl=sl+1)
			else:
				cmds.radioButtonGrp(rb2, e=True, sl=sl-3)

			cmds.textField(tf1, e=True, aie=True, ec="import maya.cmds\nmaya.cmds.setFocus('"+tf2+"')", cc=self.__moduleName+".menuBuilderCallback(method='changeText', item='"+p.id+"', textField='"+tf1+"', field='name', frameLayout='"+fr+"')")
			cmds.textField(tf2, e=True, aie=True, ec="import maya.cmds\nmaya.cmds.setFocus('"+tf3+"')", cc=self.__moduleName+".menuBuilderCallback(method='changeText', item='"+p.id+"', textField='"+tf2+"', field='short')")
			cmds.textField(tf3, e=True, aie=True, ec="import maya.cmds\nmaya.cmds.setFocus('"+tf1+"')", cc=self.__moduleName+".menuBuilderCallback(method='changeText', item='"+p.id+"', textField='"+tf3+"', field='default')")
			cmds.textField(tf1, e=True, rfc=self.__moduleName+".menuBuilderCallback(method='changeItem', item='"+p.id+"')")
			cmds.textField(tf2, e=True, rfc=self.__moduleName+".menuBuilderCallback(method='changeItem', item='"+p.id+"')")
			cmds.textField(tf3, e=True, rfc=self.__moduleName+".menuBuilderCallback(method='changeItem', item='"+p.id+"')")

			cmds.checkBox(cb1, e=True, cc=self.__moduleName+".menuBuilderCallback(method='changeCheckBox', item='"+p.id+"', checkBox='"+cb1+"', shortField='"+tf2+"')")

			def f(x,y): return x+','+y
			cmds.radioButtonGrp(rb1, e=True, cc=self.__moduleName+".menuBuilderCallback(method='changeRadio', item='"+p.id+"', radioButtonGrp='"+rb1+"', valuesButton='"+b2+"', labels='"+reduce(f, optionTypes()[:4])+"', textField='"+tf3+"')")
			cmds.radioButtonGrp(rb2, e=True, cc=self.__moduleName+".menuBuilderCallback(method='changeRadio', item='"+p.id+"', radioButtonGrp='"+rb2+"', valuesButton='"+b2+"', labels='"+reduce(f, optionTypes()[4:])+"', textField='"+tf3+"')")

			if p.positional ==  "True":
				cmds.textField(tf2, e=True, en=False)

			selected = optionTypes().index(p.type)
			if selected < 4:
				cmds.button(b2, e=True, en=False)
			else:
				cmds.button(b2, e=True, en=True)

			cmds.setFocus(tf1)
			p.tx = tf1


	def	showValues(self, layout):
		cmds.setParent(layout)
		if cmds.columnLayout("itemList", q=True, ex=True):
			cmds.deleteUI("itemList")

		pl = cmds.columnLayout("itemList", adj=True)

		for p in self.__menu.getList():
			fr = cmds.frameLayout(p=pl, cll=True, l=p.strings["name"], cl=p.collapse=="True")
			cmds.frameLayout(fr, e=True, cc=self.__moduleName+".menuBuilderCallback(method='collapseFrame', collapse='True', item='"+p.id+"')")
			cmds.frameLayout(fr, e=True, ec=self.__moduleName+".menuBuilderCallback(method='collapseFrame', collapse='False', item='"+p.id+"')")
			p.frame = fr

			firstColWidth = 60
			secondColWidth = 210
			thirdColWidth = 65

			fl = cmds.formLayout(p=fr, h=30)
			t1 = cmds.text(l="Name:", w=firstColWidth, al="left")
			tf1 = cmds.textField(tx=p.strings["name"], w=secondColWidth)
			cmds.formLayout(fl, e=True, af=[(t1, "top", 9), (t1, "left", 5)], an=[(t1, "bottom"), (t1, "right")])
			cmds.formLayout(fl, e=True, af=[(tf1, "top", 7), (tf1, "right", thirdColWidth)], ac=[(tf1, "left", 0, t1)], an=[(tf1, "bottom")])

			cmds.textField(tf1, e=True, aie=True, cc=self.__moduleName+".menuBuilderCallback(method='changeText', item='"+p.id+"', textField='"+tf1+"', field='name', frameLayout='"+fr+"')")
			cmds.textField(tf1, e=True, rfc=self.__moduleName+".menuBuilderCallback(method='changeItem', item='"+p.id+"')")
			cmds.setFocus(tf1)
			p.tx = tf1


	def	loadMenu(self):
		if len(self.__menu.getList()) > 0:
			if cmds.confirmDialog(t=self.__moduleName, m='The current menu is not empty. Are you sure?', b=['Yes','No'], db='No', cb='No', ds='No') == 'No':
				return
		parent = self.__menu.parent
		root = False
		if self.__rootMenu == self.__menu:
			root = True
		self.__menu = menuClass(self.__moduleName, "", self.__menu.parent)
		if root:
			self.__rootMenu = self.__menu
		f = cmds.fileDialog(m=0)
		if f:
			file = open(f, "rb")
			self.__menu.parseCSV(file)
			file.close()
			if isinstance(parent, menuItemClass):
				parent.menu = self.__menu
			self.showMenu()


	def	saveMenu(self):
		f = cmds.fileDialog(m=1)
		if f:
			file = open(f, "wb")
			self.__menu.generateCSV(file)
			file.close()


	def	savePromptCallback(self, **keywords):
		self.__menu.id = cmds.textField(keywords['textField'], q=True, tx=True).strip()
		if 'autoload' in keywords:
			self.__menu.autoload = str(cmds.checkBox(keywords['autoload'], q=True, v=True))
		if 'initOpt' in keywords:
			self.__menu.initOpt = str(cmds.checkBox(keywords['initOpt'], q=True, v=True))


	def	saveShelf(self):
		def savePrompt():
			form = cmds.setParent(q=True)
			cmds.formLayout(form, e=True, w=200)
			tf = cmds.textField(tx=self.__menu.id, w=100)
			self.__menu.getAutoload()
			cb1 = cmds.checkBox(l='Autoload', v=self.__menu.autoload=="True")
			cb2 = cmds.checkBox(l='Init Opt', v=self.__menu.initOpt=="True")
			b1 = cmds.button(l='  OK  ', w=80, h=25, c='import maya.cmds\nmaya.cmds.layoutDialog( dis="OK" )')
			b2 = cmds.button(l='Cancel', w=80, h=25, c='import maya.cmds\nmaya.cmds.layoutDialog( dis="Cancel" )')
			cmds.formLayout(form, e=True, af=[(tf, 'top', 10), (tf, 'left', 10)], an=[(tf, 'bottom'), (tf, 'right')])
			cmds.formLayout(form, e=True, af=[(cb1, 'top', 12)], an=[(cb1, 'bottom'), (cb1, 'right')], ac=[(cb1, 'left', 10, tf)])
			cmds.formLayout(form, e=True, ac=[(cb2, 'top', 0, cb1), (cb2, 'left', 10, tf)], an=[(cb2, 'bottom'), (cb2, 'right')])
			cmds.formLayout(form, e=True, af=[(b1, 'left', 10)], ac=[(b1, 'top', 15, cb2)], an=[(b1, 'right'), (b1, 'bottom')])
			cmds.formLayout(form, e=True, an=[(b2, 'right'), (b2, 'bottom')], ac=[(b2, 'top', 15, cb2), (b2, 'left', 10, b1)])
			cmds.textField(tf, e=True, aie=True, ec="import maya.cmds\nmaya.cmds.setFocus('"+cb1+"')", cc=self.__moduleName+".menuBuilderCallback(method='savePromptCallback', textField='"+tf+"', autoload='"+cb1+"', initOpt='"+cb2+"')")
			cmds.checkBox(cb1, e=True, cc=self.__moduleName+".menuBuilderCallback(method='savePromptCallback', textField='"+tf+"', autoload='"+cb1+"')")
			cmds.checkBox(cb2, e=True, cc=self.__moduleName+".menuBuilderCallback(method='savePromptCallback', textField='"+tf+"', initOpt='"+cb2+"')")
			cmds.setFocus(tf)
		version = int(cmds.about(v=True)[:4])
		while True:
			if version > 2010:
				result = cmds.layoutDialog(t="Save menu", ui=savePrompt)
			else:
				result = cmds.promptDialog(t="Save menu", m="(one word only)", b=['OK','Cancel'], db='OK', cb='Cancel', ds='Cancel')
			if result == "OK":
				if version < 2011:
					self.__menu.id = cmds.promptDialog(q=True, tx=True)
				if not self.__menu.id:
					continue
				cmds.optionVar(sv=(self.__moduleName+".menuBuilder.menu", self.__menu.id))
				class temp:
					buffer = ""
					def	__init__(self):
						self.buffer = ""
					def	write(self, content):
						self.buffer += content
					def writerow(self, content):
						self.buffer += content + "\n"
				tempfile = temp()
				self.__menu.generateCSV(tempfile)
				currentTab = cmds.tabLayout(self.__gShelfTopLevel, q=True, st=True)
				previousTab = currentTab
				if cmds.optionVar(ex=self.__moduleName+".selectShelf.shelf"):
					currentTab = cmds.optionVar(q=self.__moduleName+".selectShelf.shelf")
					if currentTab in cmds.tabLayout(self.__gShelfTopLevel, q=True, ca=True):
						cmds.tabLayout(self.__gShelfTopLevel, e=True, st=currentTab)
					else:
						currentTab = previousTab
				cmds.setParent(currentTab)
				done = False
				tempfile.buffer += self.__moduleName+".buildMenu('"+self.__menu.id+"')"
				if cmds.shelfLayout(currentTab, q=True, ca=True):
					for b in cmds.shelfLayout(currentTab, q=True, ca=True):
						if cmds.shelfButton(b, q=True, ex=True):
							if self.__menu.id == cmds.shelfButton(b, q=True, l=True):
								cmds.shelfButton(b, e=True, c=tempfile.buffer.strip().replace("\r\n","\r"))
								done = True
				if not done:
					mel.eval("scriptToShelf \""+self.__menu.id+"\" \""+tempfile.buffer.strip().replace("\r\n","\\r").replace("\"","\\\"")+"\" \"0\"")
				cmds.tabLayout(self.__gShelfTopLevel, e=True, st=previousTab)
				self.__menu.setAutoload()
				if self.__menu.initOpt == "True":
					self.__menu.initOptions()
				cmds.deleteUI(self.__window)
			return


	def	loadShelf(self, menuId=None):
		mns = menuOptions2()
		if not menuId or (menuId and menuId == menuOptions()[0]) or menuId not in mns:
			i = 0
			menuId = "Menu0"
			while menuId in mns:
				i = i+1
				menuId = "Menu"+str(i)

		self.__menu = menuClass(self.__moduleName, menuId)
		self.__menu.open(menuId)
		self.__rootMenu = self.__menu


	def	importFiles(self):
		if int(cmds.about(v=True)[:4]) > 2010:
			files = cmds.fileDialog2(ds=2, fm=4, cap="Select source files", ff="Source Files (*.mel *.py *.mll)")
		else:
			files = cmds.fileDialog(m=0, dm="*.mel;*.py;*.mll")
		if files:
			if not isinstance(files, types.ListType):
				files = [files]
			dir = os.path.dirname(files[0])
			files2 = jc.files.findgrep(os.path.abspath(dir), ["^global\\s+proc|^def\s+\w+"], shellglobs=["*.mel", "*.py"], findSubdir=False, progressWin=True)
			# mel, python
			if files2:
				melProc = re.compile("^global\s+proc\s+.*?(\w+)\s*\(", re.M)
				melProc2 = re.compile("^global\s+proc\s+.*?(\w+)\s*\(((?:\s*\w+\s*\$\w+(?:\[\])?\s*,)*)\s*(?:(\w+)\s*\$(\w+(?:\[\])?))?\s*\)", re.M)
				pyDef = re.compile("^def\s+(\w+)\s*\(", re.M)
				pyDef2 = re.compile("^def\s+(?P<func>\w+)\s*\((?:(?:(?P<pArg1>(?:\s*\*{0,2}\w+\s*,)*)\s*(?:(?P<pArg2>\*{0,2}\w+)\s*,|(?P<pArg3>\*{0,2}\w+)\s*))??(?:(?P<kArg1>(?:\s*\w+\s*=\s*(?:.+?)\s*,)*)\s*(?P<kArg2>\w+)\s*=\s*(?P<kDef2>.+?))?\s*)?\)", re.M)
				r = { 'mel':melProc, 'py':pyDef }
				p = { 'mel':melProc2, 'py':pyDef2 }
				typ = { 'mel':'mel', 'py':'python' }
				for file,line in files2.items():
					file = file.replace('\\','/')
					if file in files:
						suffix = os.path.basename(file).split('.')[-1]
						commands = r[suffix].findall(line)
						defs = {}
						for i in p[suffix].findall(line):
							defs[i[0]] = i[1:]
						if commands:
							for command in commands:
								if suffix == 'py':
									dir, module = self.__menu.splitPath(typ[suffix], file)
									itm = self.__menu.add(name=command, command=module+"."+command, type=typ[suffix], depend=file)
									if command in defs:
										args = re.findall("\*{0,2}\w+", defs[command][0])
										if defs[command][1]:
											args.append(defs[command][1])
										if defs[command][2]:
											args.append(defs[command][2])
										for pArg in args:
											if not pArg.startswith("*"):
												itm.add(pArg, positional="True")
										args = re.findall("(\w+)\s*=\s*(\[\s*.+?\s*\]|{\s*.+?\s*}|.+?)\s*,", defs[command][3])
										if defs[command][4] and defs[command][5]:
											args.append((defs[command][4], defs[command][5]))
										for kArg,kDef in args:
											kTyp = 'float'
											if kDef.startswith("'") or kDef.startswith('"'):
												kTyp = 'str'
												kDef = kDef.strip('"').strip("'")
											elif kDef.startswith("["):
												kTyp = 'checkbox'
											elif kDef == "True" or kDef == "False":
												kTyp = 'bool'
											elif kDef.isdigit():
												kTyp = 'int'
											elif kDef.startswith("{"):
												print "Argument skipped:",kArg,"=",kDef
												continue
											opt = itm.add(kArg, type=kTyp, short=kArg, default=kDef, positional="False")
											if kTyp == 'checkbox':
												values = kDef.strip("[]").split(",")
												if values:
													[ opt.add(x.strip('"').strip("'")) for x in values ]
									else:
										raise Exception, "syntax error with Python file while looking for arguments"
								else:
									itm = self.__menu.add(name=command, command=command, type=typ[suffix], depend=file)
									if command in defs:
										t = { 'string':'str', 'int':'int', 'float':'float', 'vector':'str', 'matrix':'str' }
										args = re.findall("(\w+)\s*\$(\w+(?:\[\])?)", defs[command][0])
										if defs[command][1] and defs[command][2]:
											args.append((defs[command][1], defs[command][2]))
										for pType,pArg in args:
											if "[]" in pArg:
												itm.add(pArg[:-2], positional="True", type='checkbox')
											else:
												itm.add(pArg, positional="True", type=t[pType])
									else:
										raise Exception, "syntax error with MEL file while looking for arguments"
			# plugin
			for file in files:
				name = os.path.basename(file)
				suffix = name.split('.')[-1]
				if suffix == 'mll':
					file = file.replace('\\','/')
					cmds.loadPlugin(file, qt=True, n=name)
					if cmds.pluginInfo(name, q=True, l=True):
						commands = cmds.pluginInfo(name, q=True, c=True)
						if commands:
							for command in commands:
								self.__menu.add(name=command, command=command, type='mel', depend=file)
			if self.__pane == "menu":
				self.showMenu()
			else:
				self.showDependencies(self.__pane)


	def	back(self, **keywords):
		if cmds.button(self.__backButton, q=True, l=True) == "Save":
			self.saveShelf()
		else:
			if isinstance(self.__menu, menuClass) and isinstance(self.__menu.parent, menuItemClass) and self.__menu.parent.type == "submenu":
				self.__menu = self.__menu.parent.parent
			elif isinstance(self.__menu, menuItemClass) and (self.__menu.type == "mel" or self.__menu.type == "python"):
				self.__menu = self.__menu.parent
			elif isinstance(self.__menu, optionClass):
				self.__menu = self.__menu.parent
			else:
				raise Exception, "unknown menu instance"
			if isinstance(self.__menu.parent, types.StringType) or isinstance(self.__menu.parent, types.UnicodeType):
				cmds.button(self.__backButton, e=True, l="Save")
			#self.show(keywords['layout'])
			self.showMenu()


	def	action(self, **keywords):
		action = keywords['action']

		if self.__pane == "menu":

			it = self.__item
			if action == "add":
				self.__item = self.__menu.add()
			elif action == 'up':
				self.__menu.up(self.__item.id, int(keywords['step']))
			elif action == 'down':
				self.__menu.down(self.__item.id, int(keywords['step']))
			elif action == 'first':
				self.__menu.first(self.__item.id)
			elif action == 'last':
				self.__menu.last(self.__item.id)
			elif action == 'delete':
				if isinstance(self.__menu, optionClass) and len(self.__menu.getList()) < 2:
					cmds.warning("at least one item is required")
					return
				self.__menu.delete(self.__item.id)
			else:
				return

			self.showMenu()
			if action in [ 'up', 'down', 'first', 'last' ]:
				it.setFocus()

		else:
			def f(x): return cmds.objectTypeUI(x) == 'textScrollList'
			textScrollLists = filter(f, cmds.layout(self.__paneLayout, q=True, ca=True))
			tsl = textScrollLists[0]
			tsl2 = textScrollLists[1]

			menu = None
			if isinstance(self.__menu, menuClass):
				menu = self.__menu
			elif isinstance(self.__menu, menuItemClass) and self.__menu.type == "submenu":
				menu = self.__menu.menu

			if action == 'browse':
				if 'popupMenu' in keywords:
					pm = keywords['popupMenu']
					paths = ['<Last directory>']+self.__menu.getEnvPaths(self.__pane)
					pm = cmds.popupMenu(pm, e=True, dai=True)
					for p in paths:
						m = cmds.menuItem(l=p, p=pm)
						cmds.menuItem(m, e=True, c=self.__moduleName+".menuBuilderCallback(method='action', action='add', menuItem='"+m+"')")

			elif action == 'add':
				filtr = { "mel":"Mel Files (*.mel)", "python":"Python Files (*.py *.pyc)", "plugin":"Plug-in Files (*.mll *.py)" }
				filtrOld = { "mel":"*.mel", "python":"*.py;*.pyc", "plugin":"*.mll;*.py" }
				files = []
				path = '<Last directory>'
				if 'menuItem' in keywords:
					path = cmds.menuItem(keywords['menuItem'], q=True, l=True)
				if path == '<Last directory>':
					if int(cmds.about(v=True)[:4]) > 2010:
						files = cmds.fileDialog2(ds=2, fm=4, cap="Select "+self.__pane+" files", ff=filtr[self.__pane])
					else:
						files = cmds.fileDialog(m=0, dm=filtrOld[self.__pane])
				else:
					if int(cmds.about(v=True)[:4]) > 2010:
						files = cmds.fileDialog2(ds=2, fm=4, cap="Select "+self.__pane+" files", dir=path, ff=filtr[self.__pane])
					else:
						files = cmds.fileDialog(m=0, dm=path+"/"+filtrOld[self.__pane])
				if files:
					if not isinstance(files, types.ListType):
						files = [files]
					[ menu.updateDependencies(self.__pane, file) for file in files ]
					self.showDependencies(self.__pane)

			elif action in [ 'delete', 'test' ]:
				items = cmds.textScrollList(tsl, q=True, si=True)
				if items:
					if action == 'delete':
						cmds.textScrollList(tsl, e=True, ri=items)
						[ menu.dependencies[self.__pane].remove(x) for x in items ]
					else:
						loadFiles(self.__pane, items, self.__rootMenu.extraPaths[self.__pane])
				elif action == 'test':
					loadFiles(self.__pane, self.__rootMenu.dependencies[self.__pane], self.__rootMenu.extraPaths[self.__pane])

				if action == 'delete':
					items = cmds.textScrollList(tsl2, q=True, si=True)
					if items:
						cmds.textScrollList(tsl2, e=True, ri=items)
						[ menu.extraPaths[self.__pane].remove(x) for x in items ]

			elif action in [ 'up', 'down', 'first', 'last' ]:
				step = int(keywords['step'])
				for t in textScrollLists:
					items = cmds.textScrollList(t, q=True, si=True)
					if items:
						ni = cmds.textScrollList(t, q=True, ni=True)
						def mv(i):
							if action == 'first': return 1
							elif action == 'last': return ni
							i = i + { 'up':-step, 'down':step }[action]
							if i < 1: return 1
							elif i > ni: return ni
							return i

						indexes = cmds.textScrollList(t, q=True, sii=True)
						z = zip(indexes, items)
						if action == 'down':
							z.reverse()

						for i,s in z:
							cmds.textScrollList(t, e=True, rii=i)
							cmds.textScrollList(t, e=True, ap=[mv(i),s])
							cmds.textScrollList(t, e=True, sii=mv(i))

						if t == tsl2:
							menu.extraPaths[self.__pane] = cmds.textScrollList(t, q=True, ai=True)
						else:
							menu.dependencies[self.__pane] = cmds.textScrollList(t, q=True, ai=True)


	def	options(self, **keywords):
		item = self.__menu.get(keywords['item'])
		self.__menu = item
		cmds.button(self.__backButton, e=True, l="Back")
		#self.show(keywords['layout'])
		self.showMenu()


	def	submenu(self, **keywords):
		item = self.__menu.get(keywords['item'])
		if item.menu:
			self.__menu = item.menu
		else:
			self.__menu = item.newMenu()
		cmds.button(self.__backButton, e=True, l="Back")
		#self.show(keywords['layout'])'
		self.showMenu()


	def	values(self, **keywords):
		item = self.__menu.get(keywords['item'])
		self.__menu = item
		if len(item.getList()) < 1:
			item.add()
		cmds.button(self.__backButton, e=True, l="Back")
		#self.show(keywords['layout'])
		self.showMenu()


	def	changeRadio(self, **keywords):
		rb = keywords['radioButtonGrp']
		selected = cmds.radioButtonGrp(rb, q=True, sl=True)-1
		item = self.__menu.get(keywords['item'])
		if 'nameField' in keywords:
			item.type = menuItemTypes()[selected]
			if selected == 0 or selected == 1:
				cmds.textField(keywords['nameField'], e=True, en=True)
				cmds.textField(keywords['commandField'], e=True, en=True)
				cmds.button(keywords['optionsButton'], e=True, en=True)
				cmds.button(keywords['submenuButton'], e=True, en=False)
				cmds.textField(keywords['annotationField'], e=True, en=True)
				cmds.checkBox(keywords['echoCheckBox'], e=True, en=True)
			elif selected == 2:
				cmds.textField(keywords['nameField'], e=True, en=False)
				cmds.textField(keywords['commandField'], e=True, en=False)
				cmds.button(keywords['optionsButton'], e=True, en=False)
				cmds.button(keywords['submenuButton'], e=True, en=False)
				cmds.textField(keywords['annotationField'], e=True, en=False)
				cmds.checkBox(keywords['echoCheckBox'], e=True, en=False)
			elif selected == 3:
				cmds.textField(keywords['nameField'], e=True, en=True)
				cmds.textField(keywords['commandField'], e=True, en=False)
				cmds.button(keywords['optionsButton'], e=True, en=False)
				cmds.button(keywords['submenuButton'], e=True, en=True)
				cmds.textField(keywords['annotationField'], e=True, en=False)
				cmds.checkBox(keywords['echoCheckBox'], e=True, en=False)
		else:
			item.type = keywords['labels'].split(',')[selected]
			if item.type in ['list', 'radio', 'checkbox']:
				cmds.button(keywords['valuesButton'], e=True, en=True)
			else:
				cmds.button(keywords['valuesButton'], e=True, en=False)
			item.strings["default"] = cmds.textField(keywords['textField'], q=True, tx=True)
			item.validateDefault()


	def	changeText(self, **keywords):
		item = self.__menu.get(keywords['item'])
		tx = cmds.textField(keywords['textField'], q=True, tx=True)
		cmdPttn = re.compile("^([0-9]|[a-z]|[A-Z]|\.|_)*$")
		def cmdFltr(x): return cmdPttn.match(x)
		field = keywords['field']
		if field == 'command':
			item.strings[field] = filter(cmdFltr, tx)
		else:
			item.strings[field] = tx
			if isinstance(item, menuItemClass):
				if item.type == 'submenu' and item.menu:
					item.menu.strings['name'] = tx
		if field == "default":
			item.validateDefault()
		if 'frameLayout' in keywords:
			cmds.frameLayout(keywords['frameLayout'], e=True, l=item.strings[field])
		cmds.textField(keywords['textField'], e=True, tx=item.strings[field])


	def	changeItem(self, **keywords):
		self.__item = self.__menu.get(keywords['item'])
		if isinstance(self.__item, optionClass):
			self.__item.validateDefault()


	def	changeCheckBox(self, **keywords):
		item = self.__menu.get(keywords['item'])
		v = str(cmds.checkBox(keywords['checkBox'], q=True, v=True))
		if isinstance(item, menuItemClass):
			item.echo = v
		elif isinstance(item, optionClass):
			item.positional = v
			cmds.textField(keywords['shortField'], e=True, en=v!="True")


	def	collapseFrame(self, **keywords):
		if keywords['item'] == 'all':
			cl = keywords['collapse']
			mnu = self.__menu
			for m in mnu.getList():
				if m.frame and cmds.frameLayout(m.frame, q=True, ex=True):
					cmds.frameLayout(m.frame, e=True, cl=cl=="True")
					m.collapse = cl
		else:
			item = self.__menu.get(keywords['item'])
			item.collapse = keywords['collapse']


	def	callback(self, **keywords):
		a = "self."+keywords['method']+"("
		for (n,v) in keywords.iteritems():
			if n != 'method':
				a += ", "+n+"='"+str(v)+"'"
		eval(a.replace(', ','',1)+")")


##	end of menuBuilderClass	##

# global variables
__menuBuilder = None
__menuBuilderCallback = None


def	menuBuilderCallback(*args, **keywords):
	__menuBuilderCallback(*args, **keywords)






def	menuBuilder(menu=None):
	# as assignment statements would make variables local implicitly, this global statement is necessary
	global __menuBuilder, __menuBuilderCallback

	if not __menuBuilder:
		__menuBuilder = menuBuilderClass(__moduleName)
		__menuBuilderCallback = __menuBuilder.callback

	__menuBuilder.showWindow(menu)


def	menuOptions2():
	gShelfTopLevel = mel.eval("$tempVar=$gShelfTopLevel")
	p = []
	currentTab = cmds.tabLayout(mel.eval("$tempVar=$gShelfTopLevel"), q=True, st=True)
	previousTab = currentTab
	if cmds.optionVar(ex=__moduleName+".selectShelf.shelf"):
		currentTab = cmds.optionVar(q=__moduleName+".selectShelf.shelf")
		if currentTab in cmds.tabLayout(gShelfTopLevel, q=True, ca=True):
			cmds.tabLayout(gShelfTopLevel, e=True, st=currentTab)
		else:
			currentTab = previousTab
	if cmds.shelfLayout(currentTab, q=True, ca=True):
		for b in cmds.shelfLayout(currentTab, q=True, ca=True):
			if cmds.shelfButton(b, q=True, ex=True):
				if cmds.shelfButton(b, q=True, c=True).lower().startswith("#menu"):
					p.append(cmds.shelfButton(b, q=True, l=True))
	cmds.tabLayout(gShelfTopLevel, e=True, st=previousTab)
	return p

def	menuOptions1():
	return [ __moduleName ] + menuOptions2()

def	menuOptions():
	return [ "Create New" ] + menuOptions2()




def	buildMenu(menu=None):
	try:
		if cmds.optionVar(ex=__moduleName+".activationCode"):
			acode = cmds.optionVar(q=__moduleName+".activationCode")
			if acode.replace('-','').lower() != bx():
				raise Exception
		else:
			raise Exception
	except:
		sys.exit("activation error")

	m = menuClass(__moduleName, menu)
	m.build()


def	shelfOptions():
	return ['<current>']+cmds.tabLayout(mel.eval("$tempVar=$gShelfTopLevel"), q=True, ca=True)


def	selectShelf(shelf=None):
	try:
		if cmds.optionVar(ex=__moduleName+".activationCode"):
			acode = cmds.optionVar(q=__moduleName+".activationCode")
			if acode.replace('-','').lower() != bx():
				raise Exception
		else:
			raise Exception
	except:
		sys.exit("activation error")

	if shelf == '<current>':
		cmds.optionVar(rm=__moduleName+".selectShelf.shelf")
	print "Self selected:",shelf


def	autoload(menus=None):
	try:
		if cmds.optionVar(ex=__moduleName+".activationCode"):
			acode = cmds.optionVar(q=__moduleName+".activationCode")
			if acode.replace('-','').lower() != bx():
				raise Exception
		else:
			raise Exception
	except:
		sys.exit("activation error")

	if menus == 0:
		menus = []
		cmds.optionVar(rm=__moduleName+".autoload.menus")
		cmds.optionVar(sva=[__moduleName+".autoload.menus",""])
		cmds.optionVar(ca=__moduleName+".autoload.menus")
	allMenus = menuOptions1()
	if not set(menus) <= set(allMenus):
		for x in list(set(menus) - set(allMenus)):
			if x in menus:
				menus.remove(x)
		cmds.optionVar(ca=__moduleName+".autoload.menus")
		if menus:
			[ cmds.optionVar(sva=[ __moduleName+".autoload.menus", x ]) for x in menus ]
	print "Autoload menus:",
	for x in menus:
		print x,
	print


def	startup():
	menus = cmds.optionVar(q=__moduleName+".autoload.menus")
	# there's a bug in Maya that empty array value [] would become 0 after restart
	if menus == 0:
		menus = [ __moduleName ]
		cmds.optionVar(rm=__moduleName+".autoload.menus")
		cmds.optionVar(sva=[__moduleName+".autoload.menus",""])
		cmds.optionVar(ca=__moduleName+".autoload.menus")
		cmds.optionVar(sva=[__moduleName+".autoload.menus",__moduleName])
	if __moduleName in menus:
		doMenu()
		menus.remove(__moduleName)
	[ buildMenu(m) for m in menus ]


def	dismiss():
	try:
		if cmds.optionVar(ex=__moduleName+".activationCode"):
			acode = cmds.optionVar(q=__moduleName+".activationCode")
			if acode.replace('-','').lower() != bx():
				raise Exception
		else:
			raise Exception
	except:
		sys.exit("activation error")

	doMenu(0)


def	addRemovePath(add, path, env):
	def f(x,y): return x+';'+y
	paths = env.split(';')
	empty = paths.count('')
	for i in range(empty):
		paths.remove('')
	if add:
		if path not in paths:
			paths.insert(0, path)
	else:
		if path in paths:
			paths.remove(path)
	return reduce(f, paths)


def	loadFiles(typ, files, paths=[]):
	env = { 'mel':'MAYA_SCRIPT_PATH', 'python':'PYTHONPATH', 'plugin':'MAYA_PLUG_IN_PATH' }
	for p in paths:
		os.environ[env[typ]] = addRemovePath(True, p, os.environ[env[typ]])
		if typ == 'python':
			sys.path.append(p)

	if typ == 'mel':
		for file in files:
			cmd = 'source "'+file.replace('\\','/')+'";'
			print cmd
			mel.eval(cmd)
		"""
		i = 0
		j = 0
		good=[]
		bad=[]
		#print "FILES",len(files),"\n"
		while j < 2:
			while i < len(files):
				try:
					cmd = 'source "'+files[i].replace('\\','/')+'";'
					print cmd
					mel.eval(cmd)
					good.append(files[i])
				except:
					bad.insert(0,files[i])
				i = i+1
			if len(bad) == 0:
				break
			files = bad
			bad = []
			j = j+1
			i = 0
			#print 'loop',j,'\n'
		#print "GOOD",len(good),"\n"
		#print "BAD",len(files),"\n"
		"""
	elif typ == 'python':
		for file in files:
			cmd = "import "+file+"\nreload("+file+")"
			print cmd
			exec(cmd)
	elif typ == 'plugin':
		for file in files:
			if not cmds.pluginInfo(os.path.basename(file), q=True, l=True):
				print "load %s" % file
				cmds.loadPlugin(file)
			else:
				print "%s is loaded" % file

	for p in paths:
		os.environ[env[typ]] = addRemovePath(False, p, os.environ[env[typ]])
		if typ == 'python' and p in sys.path:
			sys.path.remove(p)


def	doMenu(do=True, parent=None):
	destroyMenu(__moduleName)

	if do:
		if parent:
			if isinstance(parent, subMenuItem):
				m = parent
			elif not (isinstance(parent, types.StringType) or isinstance(parent, types.UnicodeType)) \
				or cmds.objectTypeUI(parent) != "floatingWindow":
				parent = None
		if not parent:
			m = createMenu(__moduleName, parent)

		i = commandItem(m, __moduleName+".menuBuilder", "Menu Builder", annotation="Open Menu Builder")
		listOption(i, "menu", menuOptions()[0], menuOptions)

		i = commandItem(m, __moduleName+".selectShelf", "Select Shelf", annotation="Show selected shelf")
		listOption(i, "shelf", shelfOptions()[0], shelfOptions)

		i = commandItem(m, __moduleName+".autoload", "Autoload", annotation="Show autoload menus")
		checkboxOption(i, "menus", [menuOptions1()[0]], menuOptions1)

		i = commandItem(m, __moduleName+".dismiss", "Dismiss", annotation="Dimiss jc.menu")
