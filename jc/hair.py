# hair.py
# This is an implementation of a hair creation tool inside Maya.
# This script has been tested with:
# - Shave and Haircut 8.0
# - Maya 2014
#
# Installation:
# This file implements the module called jc.hair.
# Under Maya script directory, create a directory called 'jc', put an empty file '__init__.py' and this file under there.
# Add PYTHONPATH to point to script directory in Maya.env.
# menu.py is prerequisite.
#
# URL:
# http://sites.google.com/site/cgriders/jc/hair
#


import types, os, random, re, copy, csv, traceback, sys, math
import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMaya as OpenMaya
import jc.menu
import jc.helper


__moduleName = "jc.hair"

__baseShape = "jcbs"
__extrudeShape = "jces"
__nearly_zero = 1.0e-10



def createHairClumps(*args, **keywords):
# usage: select NURBS patches (or their parent group) and it'll create surface curves out from the patches along hairDirection
# one patch will make one hair clump or one group of curves
# curves will be parented under the corresponding NURBS patch

	if set(keywords.keys()) != set(['hairDirection', 'extract', 'curveCount', 'visibleOnly']):
		raise Exception, "argument error"
	hairDirection 		= keywords['hairDirection']
	extract 			= keywords['extract']
	curveCount 			= keywords['curveCount']
	visibleOnly 		= keywords['visibleOnly']

	if hairDirection not in directionOptions():
		raise Exception, "invalid argument: hairDirection="+hairDirection

	if extract not in extractOptions():
		raise Exception, "invalid argument: extract="+extract

	if curveCount < 2:
		raise Exception, "curve count cannot be smaller than 2"

	extractDirection = [ x for x in directionOptions() if x != hairDirection ][0]
	extractDirection = extractDirection.lower()
	clumps = []

	if args:
		cmds.select(args, r=True)

	patches = cmds.listRelatives(ad=True, f=True, typ="nurbsSurface")
	
	if not patches:
		raise Exception, "invalid selection"
		
	patches = cmds.listRelatives(patches, p=True, f=True)
	
	if patches and visibleOnly:
		def f(x): return cmds.getAttr(x+".visibility")
		patches = filter(f, patches)

	curves = []
	for patch in patches:
		if extract == extractOptions()[0]:
			mm = cmds.getAttr(patch+".mn"+extractDirection)
			nn = (cmds.getAttr(patch+".mx"+extractDirection) - mm) / float(curveCount-1)
			for i in range(curveCount):
				#curves.append(cmds.parent(cmds.duplicateCurve(patch+"."+extractDirection+"["+str(mm)+"]", ch=True, rn=False, local=False)[0], patch)[0])
				curves.append(cmds.duplicateCurve(patch+"."+extractDirection+"["+str(mm)+"]", ch=True, rn=False, local=False)[0])
				mm += nn
		else:
			cmds.select(patch, r=True)
			for mm in jc.helper.getKnots(extractDirection):
				#curves.append(cmds.parent(cmds.duplicateCurve(patch+"."+extractDirection+"["+str(mm)+"]", ch=True, rn=False, local=False)[0], patch)[0])
				curves.append(cmds.duplicateCurve(patch+"."+extractDirection+"["+str(mm)+"]", ch=True, rn=False, local=False)[0])

	return curves




def modifyAllHairSystems(attr, value):

	hairsystems = cmds.ls(typ="hairSystem")

	for h in hairsystems:
		cmds.setAttr(h+'.'+attr, value)


def	deleteHairSystems(hairSystems):
	if type(hairSystems) != types.ListType:
		hairSystems = [ hairSystems ]
	for hairSystem in hairSystems:
		curves = cmds.ls(cmds.listHistory(hairSystem ,f=True), typ='nurbsCurve')
		if curves:
			grp = getTopGroups(curves)[0]
		follicles = cmds.ls(cmds.listHistory(hairSystem ,f=True), typ='follicle')
		if follicles:
			grp1 = getTopGroups(follicles)[0]
		cmds.select(hairSystem, r=True)
		mel.eval("deleteEntireHairSystem")
		if not cmds.listRelatives(grp):
			cmds.delete(grp)
		if not cmds.listRelatives(grp1):
			cmds.delete(grp1)


def deleteAllHairSystems():
# obsolete
	cmds.select(cmds.ls(typ="hairSystem"), r=True)
	mel.eval("deleteEntireHairSystem")


def deleteAllHairTubeShaders():
# obsolete
	hairtubeshaders = cmds.ls(typ="hairTubeShader")

	for h in hairtubeshaders:
		cmds.delete(cmds.listConnections(h + ".outColor", s=False, d=True) + [h])


def deleteAllBrushes():
# obsolete
	cmds.delete(cmds.ls(typ="brush"))


def connectShaveNodes(attributes):
# usage: select shave display meshes from outliner, then ctrl-select the master to make it appear at the end of the selection list

	shavenodes = cmds.listRelatives(ad=True, f=True, typ="shaveHair")

	if not shavenodes:
		raise Exception, "No shaveHair selected"

	if len(shavenodes) < 2:
		raise Exception, "No or not enough shaveHair is selected"

	master = shavenodes[-1]

	for s in shavenodes[:-1]:
		for a in attributes:
			if not cmds.isConnected(master+"."+a, s+"."+a):
				cmds.connectAttr(master+"."+a, s+"."+a, f=True)


def disconnectShaveNodes():
# usage: select shave display meshes from outliner

	shavenodes = cmds.listRelatives(ad=True, f=True, typ="shaveHair")

	if not shavenodes:
		raise Exception, "No shaveHair selected"

	for s in shavenodes:
		for a in getShaveHairAttributes():
			p = cmds.listConnections(s+"."+a, s=True, d=False)
			if p:
				q=cmds.listRelatives(p[0], ad=True, f=True, typ="shaveHair")
				if q:
					cmds.disconnectAttr(q[0]+"."+a, s+"."+a)


def	deleteNode(node):
	if not node or not cmds.objExists(node):
		return True

	if cmds.referenceQuery(node, inr=True):
		return False

	if cmds.objectType(node) != "objectSet":
		try:
			cmds.lockNode(node, l=False)
		except:
			pass

	try:
		cmds.delete(node)
	except:
		return False
	return True


def	deleteShaveNode(shaveHairShape):
	mel.eval("shave_cancelLive()")

	sets = None
	if cmds.attributeQuery("growthSet", n=shaveHairShape, ex=True) and cmds.attributeQuery("collisionSet", n=shaveHairShape, ex=True):
		sets = cmds.listConnections(shaveHairShape+".growthSet", shaveHairShape+".collisionSet", type="objectSet", s=True, d=False)
	elif cmds.attributeQuery("growthObjectsGroupID", n=shaveHairShape, ex=True) and cmds.attributeQuery("collisionObjectsGroupID", n=shaveHairShape, ex=True):
		sets = cmds.listConnections(shaveHairShape+".growthObjectsGroupID", shaveHairShape+".collisionObjectsGroupID", type="groupId", s=True, d=False)
	if sets:
		[ deleteNode(x) for x in sets ]

	if cmds.nodeType(shaveHairShape) == "shaveHair":
		hairShapeTransform = cmds.listRelatives(shaveHairShape, p=True, f=True)

	displayNode = mel.eval('shave_getDisplayNode("'+shaveHairShape+'")')

	deleteNode(shaveHairShape)

	if displayNode:
		displayParent = cmds.listRelatives(displayNode, p=True, f=True)
		deleteNode(displayNode)
		if displayParent:
			if not cmds.listRelatives(displayParent):
				deleteNode(displayParent[0])

	if hairShapeTransform and cmds.objExists(hairShapeTransform[0]):
		if not cmds.listRelatives(hairShapeTransform):
			deleteNode(hairShapeTransform[0])


def	deleteShaveNodes(deleteInputCurves=True):
# usage: select patches

	l = cmds.ls(sl=True)
	shavenodes = cmds.listRelatives(ad=True, f=True, typ="shaveHair")

	if not shavenodes:
		raise Exception, "No shaveHair node selected"

	for s in shavenodes:
		curves = cmds.listConnections(s+".inputCurve", s=True, d=True)
		p = cmds.listRelatives(curves, p=True, f=True)
		pp = cmds.listRelatives(p, p=True, f=True)
		#mel.eval("shaveSetCurrentNode "+s)	# fix for shave v5
		#mel.eval("shaveDelete")
		deleteShaveNode(s)
		if not cmds.objExists(s) and deleteInputCurves:
			cmds.delete(curves)
			if not cmds.listRelatives(p, ad=True, f=True):
				cmds.delete(p)
				if not cmds.listRelatives(pp, ad=True, f=True):
					cmds.delete(pp)


def modifyShaveNodes(attr, value):
# usage: select shave display meshes from outliner

	shavenodes = cmds.listRelatives(ad=True, f=True, typ="shaveHair")

	if not shavenodes:
		raise Exception, "No shaveHair selected"

	for s in shavenodes:
		try:
			mel.eval("editRenderLayerAdjustment " + s+"."+attr)
		except:
			pass
		cmds.setAttr(s+"."+attr , value)


def createHairSystems(*args, **keywords):
# usage: select NURBS patches (or their parent group) and it'll create hair systems with the indicated preset and resulting curves
#	hairDirection: direction along which curves will be extracted, "V" or "U"
#	extract: how curves will be extracted, "Isoparms" or "Curve Count"
#	curveCount: number of curves extracted from the selected surface (used if extract="Curve Count")
#	hairSystemPreset: Hair System preset name
# return: list of hair systems
#
# the requirement for the NURBS patches is the same as that for createHairClumps
# one patch will make one hair system which will be parented under the patch

	if set(keywords.keys()) != set(['hairDirection', 'extract', 'curveCount', 'visibleOnly', 'hairSystemPreset']):
		raise Exception, "argument error"
	hairDirection 		= keywords['hairDirection']
	extract 			= keywords['extract']
	curveCount 			= keywords['curveCount']
	visibleOnly 		= keywords['visibleOnly']
	hairSystemPreset 	= keywords['hairSystemPreset']

	if hairDirection not in directionOptions():
		raise Exception, "invalid argument: hairDirection="+hairDirection

	if extract not in extractOptions():
		raise Exception, "invalid argument: extract="+extract

	if curveCount < 2:
		raise Exception, "curve count cannot be smaller than 2"
		
	if hairSystemPreset and hairSystemPreset != "None":
		presetPath = os.path.join(cmds.internalVar(ups=True), "attrPresets", "hairSystem", hairSystemPreset + ".mel")
		if not os.path.isfile(presetPath):
			raise Exception, "hairSystem preset "+hairSystemPreset+" does not exist"

	if args:
		cmds.select(args, r=True)

	patches = cmds.listRelatives(ad=True, type='nurbsSurface', f=True)
	
	if not patches:
		raise Exception, "invalid selection"

	def f(x): return not cmds.getAttr(x+".intermediateObject")
	patches = cmds.listRelatives(filter(f, patches), p=True, f=True)

	hairsysList = []

	for patch in patches:
		hairSystems = cmds.listRelatives(patch, ad=True, f=True, typ='hairSystem')
		if hairSystems:
			for h in cmds.listRelatives(hairSystems, p=True, f=True):
				if h.split('|')[-1].startswith(hairSystemPreset):
					hairsysList.append(h)
					continue
					#raise Exception, "hair system of the same preset has already been created"
		cmds.setAttr(patch+".castsShadows", 0)
		cmds.setAttr(patch+".receiveShadows", 0)
		cmds.setAttr(patch+".primaryVisibility", 0)
		cmds.setAttr(patch+".visibleInReflections", 0)
		cmds.setAttr(patch+".visibleInRefractions", 0)
		cmds.setAttr(patch+".miFinalGatherCast",0)
		cmds.setAttr(patch+".miFinalGatherReceive",0)
		cmds.setAttr(patch+".miRefractionReceive",0)
		cmds.setAttr(patch+".miReflectionReceive",0)
		cmds.setAttr(patch+".miTransparencyReceive",0)
		cmds.setAttr(patch+".miTransparencyCast",0)
		curves = createHairClumps(patch, hairDirection=hairDirection, extract=extract, curveCount=curveCount, visibleOnly=visibleOnly)
		if curves:
			cmds.select(curves, r=True)
			mel.eval("makeCurvesDynamicHairs 1 0 1")
			hairsys = cmds.rename(cmds.listRelatives(cmds.ls(sl=True, l=True), p=True, f=True), hairSystemPreset+"HairSystem")
			# Change Point Lock of follicles to Base
			for i in range(cmds.getAttr(hairsys+".inputHair", s=True)):
				f = cmds.listConnections(hairsys+".inputHair["+str(i)+"]")[0]
				cmds.setAttr(f+".pointLock", 1)
				cmds.setAttr(f+".simulationMethod", 1)

			if hairSystemPreset and hairSystemPreset != "None":
				__applyAttrPreset(cmds.listRelatives(hairsys, s=True, f=True)[0], hairSystemPreset)

			cmds.select(hairsys, r=True)
			mel.eval("assignBrushToHairSystem")
			pfx = cmds.ls(sl=True, l=True)
	
			# delete brush
			cmds.delete(cmds.listConnections(pfx[0]+".brush", d=False, s=True))
	
			hairsysList.append(cmds.ls(cmds.parent(cmds.pickWalk(hairsys, d='up'), patch), l=True)[0])
			cmds.parent(cmds.pickWalk(pfx[0], d='up'), patch)

	return hairsysList


def	getTopGroups(s):
	grps = cmds.listRelatives(s, p=True, f=True)
	while cmds.listRelatives(grps, p=True, f=True):
		grps = cmds.listRelatives(grps, p=True, f=True)
	return list(set(grps))


def convertPFX2Shave(*args, **keywords):
# usage: select pfxHairs and it'll create shave nodes with the indicated preset
# return: list of shave nodes
# It would fail the first time it runs or shave plugin is not loaded

	required = set(['shavePreset', 'matchHairCount', 'shaveNodes'])
	if set(keywords.keys()) & required != required:
		raise Exception, "argument error"
	shavePreset 		= keywords['shavePreset']
	matchHairCount		= keywords['matchHairCount']
	shaveNodes 			= keywords['shaveNodes']
	deleteHistory		= True
	if cmds.optionVar(ex=__moduleName+".deleteHistory"):
		deleteHistory = cmds.optionVar(q=__moduleName+".deleteHistory")
	if 'deleteHistory' in keywords: deleteHistory = keywords['deleteHistory']

	if not cmds.pluginInfo('shaveNode',q=True,l=True):
		raise Exception, "shaveNode plugin has not been not loaded"

	presetPath = os.path.join(os.environ["MAYA_LOCATION"], "presets", "attrPresets", "shaveHair", "SPDefault.mel")
	if shavePreset and shavePreset != "None":
		presetPath = os.path.join(cmds.internalVar(ups=True), "attrPresets", "shaveHair", shavePreset + ".mel")
		if not os.path.isfile(presetPath):
			raise Exception, "shaveHair preset "+shavePreset+" does not exist"

	if args:
		cmds.select(args, r=True)

	pfxes = cmds.listRelatives(ad=True, f=True, typ="pfxHair")
	if not pfxes:
		raise Exception, "no pfxHair is selected"

	pfxes = cmds.listRelatives(pfxes, p=True, f=True)

	if shaveNodes not in shaveNodesOptions():
		raise Exception, "invalid argument: shaveNodes="+shaveNodes

	clumps = []
	for pfx in pfxes:
		patch = cmds.listRelatives(pfx, p=True, f=True)
		shaveHairs = cmds.listRelatives(patch, ad=True, f=True, typ='shaveHair')
		if shaveHairs:
			for s in cmds.listRelatives(shaveHairs, p=True, f=True):
				if s.split('|')[-1].startswith(shavePreset):
					raise Exception, "shave node of the same preset has already been created"
		p = cmds.listRelatives(pfx, ad=True, f=True, typ="pfxHair")
		if p:
			cmds.select(p, r=True)
			cmds.setAttr(p[0]+".visibility", 1)
			mel.eval("doPaintEffectsToCurve(0)")
			cmds.setAttr(p[0]+".visibility", 0)

			# delete history of paint effect curves
			s = cmds.listConnections(p[0]+".outMainCurves", d=True, s=False)
			if not s:
				raise Exception, "no output curve from pfx: "+p[0]
			cmds.select(s, r=True)
			if deleteHistory:
				mel.eval("DeleteHistory")
			clumps.append(cmds.parent(getTopGroups(s)[0], patch)[0])
			s = cmds.listConnections(p, t='hairSystem')
			if s:
				if deleteHistory:
					#cmds.select(s, r=True)
					#mel.eval("deleteEntireHairSystem")
					deleteHairSystems(s)

	if not clumps:
		raise Exception, "empty clump"
	cmds.select(clumps, r=True)
	return convertClumps2Shave(shavePreset=shavePreset, matchHairCount=matchHairCount, shaveNodes=shaveNodes)


def	convertClumps2Shave(*args, **keywords):
# usage: select clumps (groups of curves)

	required = set(['shavePreset', 'matchHairCount', 'shaveNodes'])
	if set(keywords.keys()) & required != required:
		raise Exception, "argument error"
	shavePreset 		= keywords['shavePreset']
	matchHairCount		= keywords['matchHairCount']
	shaveNodes 			= keywords['shaveNodes']

	deleteHistory = True
	if cmds.optionVar(ex=__moduleName+".deleteHistory"):
		deleteHistory = cmds.optionVar(q=__moduleName+".deleteHistory")
	if 'deleteHistory' in keywords:	deleteHistory = keywords['deleteHistory']

	if not cmds.pluginInfo('shaveNode',q=True,l=True):
		raise Exception, "shaveNode plugin has not been not loaded"

	presetPath = os.path.join(os.environ["MAYA_LOCATION"], "presets", "attrPresets", "shaveHair", "SPDefault.mel")
	if shavePreset and shavePreset != "None":
		presetPath = os.path.join(cmds.internalVar(ups=True), "attrPresets", "shaveHair", shavePreset + ".mel")
		if not os.path.isfile(presetPath):
			raise Exception, "shaveHair preset "+shavePreset+" does not exist"

	if args:
		cmds.select(args, r=True)

	clumps = cmds.ls(sl=True, l=True)
	shaveList = []

	if shaveNodes == shaveNodesOptions()[1]:
		clumps = [ clumps ]

	for clump in clumps:
		doit = True
		shaveHairs = cmds.listConnections(cmds.listRelatives(clump, ad=True, f=True, typ='nurbsCurve'), t='shaveHair')
		if shaveHairs:
			for s in cmds.listRelatives(shaveHairs, p=True, f=True):
				if s.split('|')[-1].startswith(shavePreset):
					doit = False
			if doit:
				if shaveNodes == shaveNodesOptions()[1]:
					raise Exception, "existing shave node found, unable to proceed with shave nodes option \"One\""
				shaveList.append(shaveHairs[0])
		if doit:
			c = cmds.listRelatives(clump, ad=True, f=True, typ='nurbsCurve')
			if c:
				cmds.select(c, r=True)
				mel.eval("shaveCreateHairFromPreset \""+presetPath.replace("\\","/")+"\"")
				n = cmds.listConnections(c[0]+".worldSpace", s=False, d=True)
				if n:
					n = cmds.rename(n[0], shavePreset+"ShaveHair")
					if matchHairCount:
						cmds.setAttr(n+".hairCount", len(c))
						if cmds.getAttr(n+".displayHairMax") < len(c):
							cmds.setAttr(n+".displayHairMax", len(c))
					p = cmds.listRelatives(clump, p=True, f=True)
					if type(clump) == types.ListType:
						p = cmds.listRelatives(clump[0], p=True, f=True)
					if p:
						n = cmds.ls(cmds.parent(n, p[0])[0], l=True)[0]
					shaveList.append(n)

	if shaveList:
		if shaveList[1:]:
			cmds.select(shaveList[1:], r=True)
		else:
			cmds.select(cl=True)
		cmds.select(shaveList[0], add=True)
		
		if len(shaveList) > 1:
			if cmds.optionVar(ex='jc.hair.connectShaveNodes.attributes'):
				connectShaveNodes(cmds.optionVar(q='jc.hair.connectShaveNodes.attributes'))
			else:
				connectShaveNodes(getShaveHairAttributes())

	return shaveList
	

def createHairs(*args, **keywords):
# usage: select NURBS patches (or their parent group) and it'll create hair systems and shave nodes with given presets

	required = set(['hairDirection', 'extract', 'curveCount', 'visibleOnly', 'matchHairCount', \
		'shaveNodes', 'hairSystemPreset', 'shavePreset', 'shaveGlobalsPreset', 'polygon'])
	if set(keywords.keys()) & required != required:
		raise Exception, "argument error"
	hairDirection 		= keywords['hairDirection']
	extract 			= keywords['extract']
	curveCount 			= keywords['curveCount']
	visibleOnly 		= keywords['visibleOnly']
	matchHairCount 		= keywords['matchHairCount']
	shaveNodes 			= keywords['shaveNodes']
	hairSystemPreset 	= keywords['hairSystemPreset']
	shavePreset 		= keywords['shavePreset']
	shaveGlobalsPreset 	= keywords['shaveGlobalsPreset']
	polygon				= keywords['polygon']

	renderLayer = None
	if cmds.optionVar(ex=__moduleName+".renderLayer"):
		renderLayer = cmds.optionVar(q=__moduleName+".renderLayer")
	if 'renderLayer' in keywords:	renderLayer = keywords['renderLayer']

	renderLayerShadow = None
	if cmds.optionVar(ex=__moduleName+".renderLayerShadow"):
		renderLayerShadow = cmds.optionVar(q=__moduleName+".renderLayerShadow")
	if 'renderLayerShadow' in keywords:	renderLayerShadow = keywords['renderLayerShadow']

	deleteHistory = True
	if cmds.optionVar(ex=__moduleName+".deleteHistory"):
		deleteHistory = cmds.optionVar(q=__moduleName+".deleteHistory")
	if 'deleteHistory' in keywords:	deleteHistory = keywords['deleteHistory']

	shave = True
	if 'shave' in keywords:	shave = keywords['shave']

	if hairDirection not in directionOptions():
		raise Exception, "invalid argument: hairDirection="+hairDirection

	if extract not in extractOptions():
		raise Exception, "invalid argument: extract="+extract

	if curveCount < 2:
		raise Exception, "curve count cannot be smaller than 2"

	if not hairSystemPreset or not shavePreset or not shaveGlobalsPreset:
		raise Exception, "Both hairSystemPreset, shavePreset and shaveGlobalsPreset must be provided"

	if shaveNodes not in shaveNodesOptions():
		raise Exception, "invalid argument: shaveNodes="+shaveNodes

	if args:
		cmds.select(args, r=True)

	patches = cmds.listRelatives(ad=True, f=True, typ='nurbsSurface')
	if not patches:
		raise Exception, "invalid selection"
	
	patches = cmds.listRelatives(patches, f=True, p=True)

	shaveList = []
	cmds.select(patches, r=True)
	hairSystems = createHairSystems(hairDirection=hairDirection, extract=extract, curveCount=curveCount, visibleOnly=visibleOnly, hairSystemPreset=hairSystemPreset)
	if hairSystems:
		pfxes = cmds.listConnections(cmds.listRelatives(hairSystems, s=True, f=True), t='pfxHair')
		if pfxes:
			if polygon:
				cmds.select(pfxes, r=True)
				fileName = patches[0].split("|")[-1]
				createPolygonHair(renderLayer=renderLayerShadow, deleteHistory=deleteHistory)
			if shave:
				cmds.select(pfxes, r=True)
				shaveList = convertPFX2Shave(shavePreset=shavePreset, matchHairCount=matchHairCount, shaveNodes=shaveNodes, deleteHistory=deleteHistory)
	
		if deleteHistory:
			hs = cmds.listRelatives(patches, ad=True, f=True, typ='hairSystem')
			if hs:
				def h(x): return x.split('|')[-1].startswith(hairSystemPreset)
				hs = filter(h, hs)
				if hs:
					#cmds.select(hs, r=True)
					#mel.eval("deleteEntireHairSystem")
					deleteHairSystems(hs)
	
		if shave and shaveGlobalsPreset and shaveGlobalsPreset != "None":
			if cmds.objExists('shaveGlobals'):
				__applyAttrPreset("shaveGlobals", shaveGlobalsPreset)
	
		if renderLayer and renderLayer != "None" and shave:
			if cmds.objExists('shaveGlobals'):
				cmds.select(patches, r=True)
				hideHairInRenderLayers(exception=renderLayer)


def createPolygonHair(*args, **keywords):
# usage: select pfxHairs on which hair systems have been created

#	required = set(['fileName'])
#	if set(keywords.keys()) & required != required:
#		raise Exception, "argument error"

#	fileName = None
#	if 'fileName' in keywords.keys(): fileName = keywords['fileName']

#	fileType = fileTypeOptions()[0]
#	if 'fileType' in keywords.keys(): fileType = keywords['fileType']

	renderLayer = None
	if 'renderLayer' in keywords.keys(): renderLayer = keywords['renderLayer']

	polyLimit = 500000
	if cmds.optionVar(ex=__moduleName+".polyLimit"):
		polyLimit = cmds.optionVar(q=__moduleName+"createPolygonHair.polyLimit")
	if 'polyLimit' in keywords.keys(): polyLimit = keywords['polyLimit']

	deleteHistory = True
	if cmds.optionVar(ex=__moduleName+".deleteHistory"):
		deleteHistory = cmds.optionVar(q=__moduleName+".deleteHistory")
	if 'deleteHistory' in keywords.keys(): deleteHistory = keywords['deleteHistory']

#	if not fileName:
#		raise Exception, "no file name given"

	if args:
		cmds.select(args, r=True)

	if not cmds.ls(sl=True) or not cmds.listRelatives(ad=True, f=True, typ='pfxHair'):
		raise Exception, "invalid selection"

	pfxes = cmds.listRelatives(ad=True, f=True, typ='pfxHair')
	objs = []
	for pfx in pfxes:
		cmds.select(pfx, r=True)

		# convert pfx to polygon
		mel.eval("doPaintEffectsToPoly( 1, 0, 0, 1, "+str(polyLimit)+" )")
		obj = cmds.listConnections(pfx+'.worldMainMesh')
		if deleteHistory:
			mel.eval("DeleteHistory")
		if obj:
			cmds.setAttr(obj[0]+".castsShadows", 1)
			cmds.setAttr(obj[0]+".receiveShadows", 0)
			cmds.setAttr(obj[0]+".primaryVisibility", 0)
			cmds.setAttr(obj[0]+".visibleInReflections", 0)
			cmds.setAttr(obj[0]+".visibleInRefractions", 0)
			cmds.setAttr(obj[0]+".miFinalGatherCast",0)
			cmds.setAttr(obj[0]+".miFinalGatherReceive",0)
			cmds.setAttr(obj[0]+".miRefractionReceive",0)
			cmds.setAttr(obj[0]+".miReflectionReceive",0)
			cmds.setAttr(obj[0]+".miTransparencyReceive",0)
			cmds.setAttr(obj[0]+".miTransparencyCast",0)

			# replace hairtube shader with surface shader
			def f(x): return cmds.nodeType(x)=="shadingEngine"
			shadingGrp = filter(f, cmds.listConnections(cmds.listRelatives(obj)))[0]
			hairtube = cmds.listConnections(shadingGrp+".surfaceShader")[0]
			#surfaceShader = cmds.createNode('surfaceShader')
			#mel.eval("replaceNode \""+hairtube+"\" \""+surfaceShader+"\"")
			cmds.delete(shadingGrp, hairtube)

			objs += obj

	surfaceShader = cmds.shadingNode("surfaceShader", asShader=True)
	cmds.select(objs, r=True)
	cmds.hyperShade(a=surfaceShader)

#	if fileName:
#		filePath = fileName
#		projectDirectory = cmds.workspace(q=True, rd=True)
#		if 'scene' in cmds.workspace(q=True, frl=True):
#			filePath = os.path.join(projectDirectory, cmds.workspace(fre='scene'), fileName)
#		if os.path.isfile(filePath+[".mb",".ma"][fileTypeOptions().index(fileType)]):
#			os.remove(filePath+[".mb",".ma"][fileTypeOptions().index(fileType)])
#		cmds.file( filePath, sh=True, es=True, typ=fileType, op="v=0", ch=not deleteHistory )

#		cmds.delete(cmds.listConnections(surfaceShader + ".outColor"))
#		cmds.delete(getTopGroups(objs), surfaceShader)

#		[ cmds.setAttr(pfx+".visibility", 1) for pfx in pfxes ]

#		print "Polygon Hair saved to "+filePath+[".mb",".ma"][fileTypeOptions().index(fileType)]

	if renderLayer and renderLayer != "None" and objs:
		cmds.editRenderLayerMembers(renderLayer, objs, nr=True)


def	__listRelatives(*args, **keywords):
	def f(x): return not cmds.getAttr(x+".intermediateObject")
	return filter(f, cmds.listRelatives(*args, **keywords))

def	__convertNURBS2Poly(*args):
# usage: select nurbs objects, they'll be converted into polygon objects which will be combined into a single object

	if args:
		cmds.select(args, r=True)

	r = re.compile("(.*?)[N|C|S|Loc|Cam|Light|RL|L|J]?_[0-9]+")
	poly = []
	for nurbs in cmds.ls(sl=True):
		nurbs1 = [nurbs]
		if cmds.nodeType(nurbs1) != "nurbsSurface":
			nurbs1 = __listRelatives(nurbs1, type='nurbsSurface', f=True)
			if not nurbs1:
				continue
		s = r.search(nurbs)
		if s and s.group(1):
			nurbs = s.group(1)
		nurbs += 'Wrap_'
		poly += cmds.nurbsToPoly(nurbs1, mnd=True, ch=False, n=nurbs, f=2, pt=1, ut=3, un=1, vt=3, vn=1, uch=False, ucr=False)
	if poly:
		if len(poly) > 1:
			return cmds.polyUnite(poly, ch=False, n=poly[0])
		else:
			return poly

def	__wrapNURBS(*args):
	if args:
		cmds.select(args, r=True)
	nurbs = cmds.ls(sl=True)
	mesh = __convertNURBS2Poly(*args)
	if mesh:
		cmds.setAttr(mesh[0]+".castsShadows", 0)
		cmds.setAttr(mesh[0]+".receiveShadows", 0)
		cmds.setAttr(mesh[0]+".primaryVisibility", 0)
		cmds.setAttr(mesh[0]+".visibleInReflections", 0)
		cmds.setAttr(mesh[0]+".visibleInRefractions", 0)
		cmds.setAttr(mesh[0]+".miFinalGatherCast",0)
		cmds.setAttr(mesh[0]+".miFinalGatherReceive",0)
		cmds.setAttr(mesh[0]+".miRefractionReceive",0)
		cmds.setAttr(mesh[0]+".miReflectionReceive",0)
		cmds.setAttr(mesh[0]+".miTransparencyReceive",0)
		cmds.setAttr(mesh[0]+".miTransparencyCast",0)
		transforms = cmds.listRelatives(__listRelatives(nurbs, type='nurbsSurface', f=True), p=True, f=True)
		# deformer cannot be connected to the NURBS patch if there's a shave node under it
		# the following code is to unparent the shave node before applying deformer
		# but in practice this process cannot be finished
		# thus wrap deformer must be applied BEFORE creating shave hair
		#pairs = []
		#if cmds.pluginInfo('shaveNode',q=True,l=True):
		#	for transform in transforms:
		#		n = cmds.listRelatives(cmds.listRelatives(transform, typ='shaveHair', ad=True, f=True), p=True, f=True)
		#		if n:
		#			pairs.append([transform, cmds.parent(n, w=True)])
		cmds.select(transforms, r=True)
		cmds.select(mesh, add=True)
		#mel.eval("performWrap 1")
		#doWrapArgList "6" {"1", "<weightThreshold>", "<maxDistance, def=0.0>", "<wrapInflType, 1=vertex, 2=face>", "<exclusiveBind>", "<autoWeightThrehold>", "<renderInfl>" }
		mel.eval('doWrapArgList "6" {"1", "0", "0", "2", "0", "0", "0" }')
		#for p in pairs:
		#	cmds.parent(p[1], p[0])
		cmds.select(mesh, r=True)
		return mesh

def	createNClothWrapDeformer(*args, **keywords):
# usage: select nurbs objects and a passive collision object
# assumption: no shave node has been created

	hairDirection = directionOptions()[1]
	if 'hairDirection' in keywords:	hairDirection = keywords['hairDirection']

	nClothPreset = None
	if 'nClothPreset' in keywords:	nClothPreset = keywords['nClothPreset']

	if args:
		cmds.select(args, r=True)

	nurbs = []
	colli = None
	solver = None
	for o in cmds.ls(sl=True):
		if cmds.nodeType(o) == "nurbsSurface" or cmds.listRelatives(o, type='nurbsSurface') != None:
			nurbs.append(o)
		solver = cmds.ls(cmds.listHistory(o, f=True), type='nucleus')
		if solver:
			colli = o
	mesh = __wrapNURBS(*nurbs)
	if mesh:
		cmds.select(mesh, r=True)
		if solver and colli:
			mel.eval("getActiveNucleusNode(true, false);")
			mel.eval("setActiveNucleusNode(\""+solver[0]+"\");")
		ncloth = mel.eval("createNCloth 0;")
		if colli and ncloth:

			def createDefaultRamp(name, position0, value0, position1, value1):
				ramp = cmds.createNode('ramp', n=name)
				cmds.removeMultiInstance(ramp+".colorEntryList[2]", b=True)
				cmds.setAttr(ramp+".colorEntryList[0].color", value0, value0, value0, type="double3")
				cmds.setAttr(ramp+".colorEntryList[0].position", position0)
				cmds.setAttr(ramp+".colorEntryList[1].color", value1, value1, value1, type="double3")
				cmds.setAttr(ramp+".colorEntryList[1].position", position1)
				if hairDirection == directionOptions()[1]:
					cmds.setAttr(ramp+".type", 0)
				else:
					cmds.setAttr(ramp+".type", 1)
				return ramp

			rampPresets = getPresets("ramp")
			prefix = "None"
			if nClothPreset: prefix = nClothPreset

			if nClothPreset and nClothPreset != "None":
				__applyAttrPreset(ncloth[0], nClothPreset)

			for map in [".rigidityMap", ".deformMap", ".dampMap", ".massMap", ".collideStrengthMap"]:
				if cmds.attributeQuery(map[1:], typ='nCloth', ex=True):
					p = prefix+map[1].upper()+map[2:]
					ramp = createDefaultRamp(p, 0.5, 1, 1, 0.231)
					cmds.connectAttr(ramp+".outAlpha", ncloth[0]+map, force=True)
					if p in rampPresets:
						__applyAttrPreset(ramp, p)

			cmds.select(cmds.polyListComponentConversion(mesh, tv=True), r=True)
			cmds.select(colli, add=True)
			constraint = mel.eval("createNConstraint pointToSurface 0")
			if constraint:
				component = list(set(cmds.ls(cmds.listHistory(ncloth, f=True), type='nComponent')) & set(cmds.ls(cmds.listHistory(constraint), type='nComponent')))
				if component:
					for map in [".strengthMap", ".glueStrengthMap"]:
						p = prefix+map[1].upper()+map[2:]
						ramp = createDefaultRamp(p, 0, 1, 0.25, 0)
						cmds.connectAttr(ramp+".outAlpha", component[0]+map, force=True)
						if p in rampPresets:
							__applyAttrPreset(ramp, p)

			outcloth = cmds.listConnections(ncloth, d=True, s=False, type='mesh', sh=True)
			if outcloth:
				cmds.setAttr(outcloth[0]+".castsShadows", 0)
				cmds.setAttr(outcloth[0]+".receiveShadows", 0)
				cmds.setAttr(outcloth[0]+".primaryVisibility", 0)
				cmds.setAttr(outcloth[0]+".visibleInReflections", 0)
				cmds.setAttr(outcloth[0]+".visibleInRefractions", 0)
				cmds.setAttr(outcloth[0]+".miFinalGatherCast",0)
				cmds.setAttr(outcloth[0]+".miFinalGatherReceive",0)
				cmds.setAttr(outcloth[0]+".miRefractionReceive",0)
				cmds.setAttr(outcloth[0]+".miReflectionReceive",0)
				cmds.setAttr(outcloth[0]+".miTransparencyReceive",0)
				cmds.setAttr(outcloth[0]+".miTransparencyCast",0)


def	__applyAttrPreset(node, preset):
	count = 2
	while count:
		try:
			mel.eval("applyAttrPreset(\""+node+"\", \""+preset+"\", 1)")
			count = 0
		except:
			mel.eval("AttributeEditor;openAEWindow;commitAENotes($gAECurrentTab);window -e -vis 0 AEWindow;")




def updateHairOcclusionObjects():
# usage: select objects and it'll update shaveGloabls.hairOcclusionObjects
# It doesn't check if the selections are renderable objects or not

	if not cmds.objExists('shaveGlobals'):
		raise Exception, "no shaveGlobals exists"

	q = cmds.ls(sl=True, l=True)
	if not q:
		raise Exception, "no object is selected"

	s = ""
	for p in q:
		s += p + " "
	cmds.setAttr("shaveGlobals.hairOcclusionObjects", s, type="string")


def	hideHairInRenderLayers(*args, **keywords):
# usage: select patches and it'll hide the corresponding shave nodes in all render layers except for excepted layer
# It would fail to work correctly if the attribute editor for shaveGlobals is currently open when a non-default render layer is chosen

	if 'exception' not in keywords.keys():
		raise Exception, "argument error"

	exception = keywords['exception']

	if not cmds.objExists('shaveGlobals'):
		raise Exception, "no shaveGlobals exists"

	if args:
		cmds.select(args, r=True)

	selection = cmds.listRelatives(ad=True, f=True, typ='nurbsSurface')
	if not selection:
		raise Exception, "invalid selection"
	selection = cmds.listRelatives(cmds.listRelatives(selection, p=True, f=True), ad=True, f=True, typ='shaveHair')
	if not selection:
		raise Exception, "no shave node found"

	p = getRenderLayersCallback()	
	p.remove('None')

	if exception and exception != 'None':
		cmds.editRenderLayerMembers(exception, selection, nr=True)
		g = "shaveDisplayGroup"
		if  cmds.objExists(g):
			cmds.editRenderLayerMembers(exception, g, nr=True)

	# create plugs
	for r in p:
		cmds.editRenderLayerAdjustment("shaveGlobals.hideHair",layer=r)

	# update plugs
	plugs = cmds.listConnections("shaveGlobals.hideHair", s=False, d=True, p=True)
	for plug in plugs:
		plug = plug.replace('plug','value')
		if exception and exception != 'None' and plug.startswith(exception):
			cmds.setAttr(plug, 0)
		else:
			cmds.setAttr(plug, 1)


def	getRenderLayersCallback():
	p = cmds.ls(typ='renderLayer')
	p.remove('defaultRenderLayer')
	p.insert(0, 'None')
	return p


def	getHairSystemPresetsCallback():
	return getPresets("hairSystem")


def	getShaveHairPresetsCallback():
	return getPresets("shaveHair")


def	getNClothPresetsCallback():
	return getPresets("nCloth")


def	getShaveGlobalsPresetsCallback():
	return getPresets("shaveGlobals")


def	getPresets(node):
	presetPaths = []
	if 'MAYA_LOCATION' in os.environ:
		presetPaths.append(os.path.join(os.environ['MAYA_LOCATION'], "attrPresets"))

	if 'MAYA_PRESET_PATH' in os.environ:
		for p in os.environ['MAYA_PRESET_PATH'].split([':',';'][cmds.about(nt=True)]):
			presetPaths.append(os.path.join(p, "attrPresets"))

	presetPaths.append(os.path.join(cmds.internalVar(ups=True), "attrPresets"))

	p = [ "None" ]
	for presetPath in presetPaths:
		if os.path.isdir(presetPath):
			for root, dirs, files in os.walk(presetPath):
				if os.path.basename(root) == node:
					for f in files:
						if f.endswith('.mel'):
							p.append(f[:-4])
	return p


def	directionOptions():
	return	[ "U", "V" ]
	

def	extractOptions():
	return	[ "Curve Count", "Isoparms" ]
	
		
def	shaveNodesOptions():
	return	[ "Many", "One" ]


def	getShaveHairAttributes():
	return	[	"hairCount", 
				"hairPasses",
			    "hairSegments",
			    "scale",
				"randScale",
				"rootThickness",
			    "tipThickness",
			    "displacement",
				"active",
				"interpolateGuides",
				"instancingStatus",
				"selfShadow",
				"geomShadow",
				"specular",
				"specularTint",
				"gloss",
				"amb/diff",
				"hairColor",
				"hueVariation",
				"valueVariation",
				"rootColor",
				"mutantHairColor",
				"percentMutantHairs",
				"tipFade",
				"overrideGeomShader",
				"rootFrizz",
				"tipFrizz",
				"frizzXFrequency",
				"frizzYFrequency",
				"frizzZFrequency",
				"rootKink",
				"tipKink",
				"kinkXFrequency",
				"kinkYFrequency",
				"kinkZFrequency",
				"multiStrandCount",
				"rootSplay",
				"tipSplay",
				"randomizeMulti",
				"displayGuides",
				"displayAs",
				"displayHairRatio",
				"displayHairMax",
				"displaySegmentLimit"
			]

def	fileTypeOptions():
	return [ "mayaBinary", "mayaAscii" ]


def	touchShaveHair():

	at = ".hairPasses"
	for s in cmds.ls(typ="shaveHair"):
		if not cmds.listConnections(s+at, s=True, d=False):
			cmds.setAttr(s+at, cmds.getAttr(s+at))


def	trim(hairDirection, ratio, randomize, trim):

	if hairDirection not in directionOptions():
		raise Exception, "invalid argument: hairDirection="+hairDirection

	if ratio < 0 or ratio > 1:
		raise Exception, "invalid argument: ratio="+str(ratio)

	if trim not in trimOptions():
		raise Exception, "invalid argument: trim="+trim

	objs = cmds.listRelatives(ad=1,typ=("nurbsSurface","nurbsCurve"),f=1)
	if not objs:
		return

	sel = []
	d = hairDirection.lower()

	for cc in objs:
		if cmds.nodeType(cc) == "nurbsSurface":
			n = cmds.getAttr(cc+".mn"+d)
			x = cmds.getAttr(cc+".mx"+d)
		else:
			c = cmds.listRelatives(cc,p=1)[0]
			n = cmds.getAttr(c+".min")
			x = cmds.getAttr(c+".max")

		p = (x-n)*ratio
		if randomize:
			p = random.uniform(0,p)
		if trim == trimOptions()[0]:
			p = n+p
		else:
			p = x-p

		if cmds.nodeType(cc) == "nurbsSurface":
			ss = cmds.detachSurface(cc+"."+d+"["+str(p)+"]",ch=0,rpo=1)
		else:
			ss = cmds.detachCurve(c,ch=0,cos=1,rpo=1,p=p)

		if trim == trimOptions()[0]:
			cmds.delete(ss[-1])
			sel += ss[:-1]
		else:
			cmds.delete(ss[0])
			sel += ss[1:]

	cmds.select(sel,r=True)


def	trimOptions():
	return [ "Start", "End" ]


def	displace(amplitude, displace):

	if amplitude < 0:
		raise Exception, "invalid argument: amplitude="+str(amplitude)
		
	if displace not in displaceOptions():
		raise Exception, "invalid argument: displace="+displace

	for cc in cmds.listRelatives(ad=True, typ=("nurbsCurve", "nurbsSurface"), f=True):
		c = cmds.listRelatives(cc,p=1)[0]
		if displace == displaceOptions()[0]:
			if cmds.nodeType(cc) == "nurbsCurve":
				cmds.rotate(random.uniform(-amplitude,amplitude),random.uniform(-amplitude,amplitude),random.uniform(-amplitude,amplitude),c,p=cmds.pointOnCurve(c,pr=cmds.getAttr(c+".min"),p=1),r=1,os=1)
			else:
				cmds.rotate(random.uniform(-amplitude,amplitude),random.uniform(-amplitude,amplitude),random.uniform(-amplitude,amplitude),c,p=cmds.pointOnSurface(c,p=1,u=cmds.getAttr(c+".mnu"),v=(cmds.getAttr(c+".mnv")+cmds.getAttr(c+".mxv"))/2),r=1,os=1)
		else:
			cmds.move(random.uniform(-amplitude,amplitude),random.uniform(-amplitude,amplitude),random.uniform(-amplitude,amplitude),c,r=1,os=1)


def	displaceOptions():
	return [ "Rotation", "Translation" ]


def	createJointChain(*args, **keywords):
# usage: select NURBS patches

	hairDirection = keywords['hairDirection']

	if hairDirection not in directionOptions():
		raise Exception, "invalid argument: hairDirection="+hairDirection

	if args:
		cmds.select(args, r=True)

	patches = cmds.ls(sl=True, l=True)
	if patches:
		patches = cmds.listRelatives(patches, ad=True, type='nurbsSurface', f=True)
		if patches:
			patches = cmds.listRelatives(patches, p=True, f=True)

			for patch in patches:
				direction = "uv".replace(hairDirection.lower(), "")
				min = cmds.getAttr(patch+'.minValue'+direction.upper())
				max = cmds.getAttr(patch+'.maxValue'+direction.upper())
				isoparm = "%s.%s[%f]" % (patch, direction, (min+max)/2)
				cmds.select(patch, r=True)
				knots = jc.helper.getKnots(direction=hairDirection)
				points = []
				for knot in knots:
					cmds.select(isoparm, r=True)
					points.append(cmds.pointOnCurve(p=True, pr=knot, top=False))

				# create joint chain
				cmds.select(cl=True)
				joint1 = cmds.joint(p=points[0])
				rootJ = joint1
				for p in points[1:]:
					joint2 = cmds.joint(p=p)
					cmds.joint(joint1, e=True, zso=True, oj='xyz', sao='yup')
					joint1 = joint2

				cmds.skinCluster(rootJ, patch)


def	createHelixPatch(*args, **keywords):

	hairDirection = keywords['hairDirection']
	radius = keywords['radius']
	height = keywords['height']
	width = keywords['width']
	coils = int(keywords['coils'])
	ch = True
	if 'constructionHistory' in keywords.keys(): ch = keywords['constructionHistory']
	sections = 8

	cylinder = cmds.cylinder(p=(0, 0, 0), ax=(0, -1, 0), ssw=0, esw=360, r=radius, hr=height/radius, d=3, s=sections, nsp=sections, ch=ch)
	minU = cmds.getAttr(cylinder[0]+'.minValueU')
	maxU = cmds.getAttr(cylinder[0]+'.maxValueU')
	minV = cmds.getAttr(cylinder[0]+'.minValueV')
	maxV = cmds.getAttr(cylinder[0]+'.maxValueV')

	coils4 = coils*4
	uv = [(minU, minV), (minU+0.02, minV+0.1)]
	k = [0, 0, 0]
	for n in range(1,coils4):
		uv.append((minU+float(n)*(maxU-minU)/coils4,minV+((maxV-minV)/4.0)*float(n)))
		k.append(n)
	uv += [(maxU-0.02, minV+(maxV-minV)*coils-0.1), (maxU, minV+(maxV-minV)*coils)]
	k += [coils4, coils4, coils4]
	curve1 = cmds.curveOnSurface(cylinder, d=3, uv=tuple(uv), k=tuple(k))

	(obj,offsetNode) = cmds.offsetCurveOnSurface(curve1, ch=True, rn=False, cb=2, st=True, cl=False, d=width, tol=0.01, sd=5)
	curve2 = cmds.listConnections(offsetNode+'.outputCurve[0]')
	if not ch:
		cmds.delete(curve2, ch=True)
	patch = cmds.loft(curve1, curve2, ch=ch, u=1, c=0, ar=1, d=3, ss=1, rn=0, po=0, rsn=True)
	if hairDirection.lower() == "v":
		cmds.reverseSurface(patch[0], d=3, ch=ch, rpo=True)


class	hairstyle:
	# paramter type is either string or list of strings
	# paramter type is changed when it's being put in or taken out from the UI controls

	layers = []
	globals = {}
	__serialLayer = 0
	__moduleName = ""

	def	__init__(self, moduleName):
		self.layers = []
		self.globals = {	\
			'turnOffUndo':"True",		\
			'hairDirection':directionOptions()[0],		\
			'extract':extractOptions()[0],	\
			'visibleOnly':"True",		\
			'shaveGlobalsPreset':getShaveGlobalsPresetsCallback()[0],	\
			'renderLayer':getRenderLayersCallback()[0],		\
			'renderLayerShadow':getRenderLayersCallback()[0],		\
			'passiveCollider': "",		\
			'deleteHistory':"True",		\
			'hairstyle':""	}
		self.__serialLayer = 0
		self.__moduleName = moduleName

	def	newItem(self, name=None):
		if name and self.getItem(name):
			raise Exception, "item already exists"
		if not name:
			name = 'layer'+str(self.__serialLayer)
		self.__serialLayer += 1
		item = {	\
			'master':name, \
			'patches':[],	\
			'curveCount':"5",	\
			'hairSystemPreset':"None",	\
			'shavePreset':"None",		\
			'nClothPreset':"None",		\
			'shaveNodes':shaveNodesOptions()[0],		\
			'matchHairCount':"True",	\
			'shave':"True",	\
			'polygon':"True",	\
			'nCloth':"True",	\
			'frameState':False	}
		self.layers.append(item)
		return item

	def	getItem(self, name):
		def f(x): return x['master'] == name
		l = filter(f, self.layers)
		if l:
			return l[0]
		return None

	def	removeItem(self, item):
		def f(x): return x['master'] == item
		l = filter(f, self.layers)
		if l:
			self.layers.remove(l[0])

	def	addItem(self, objects):
		objects = [x for x in objects if cmds.objExists(x) and cmds.listRelatives(x, typ='nurbsSurface')]
		if objects:
			s = self.newItem(objects[0])
			s['master'] = objects[0]
			s['patches'] = objects[1:]
			return
		raise Exception, "no selection or selection invalid"


	def	getNodes(self, master, type):
		i = self.getItem(master)
		if not i:
			raise Exception, "no such master"

		def f(x):
			prefix = { 'hairSystem': 'hairSystemPreset', 'shaveHair': 'shavePreset' } 
			return x.split('|')[-1].startswith(i[prefix[type]]+type[0].upper()+type[1:])

		nodes = []
		for p in [ i['master'] ] + i['patches']:
			n = cmds.listRelatives(p, ad=True, f=True, typ=type)
			if n:
				n = filter(f, n)
				if n:
					nodes += n
		return nodes

		
	def	testMaster(self, master):
		i = self.getItem(master)
		if not i:
			raise Exception, "no such master"

		if not cmds.pluginInfo('shaveNode',q=True,l=True):
			raise Exception, "shaveNode plugin has not been not loaded"

		hairSystems = self.getNodes(i['master'], 'hairSystem')
		shaveHairs = self.getNodes(i['master'], 'shaveHair')

		if hairSystems:
			if shaveHairs:
				cmds.select(cmds.listRelatives(shaveHairs, p=True, f=True), r=True)
				deleteShaveNodes(deleteInputCurves=True)
				deleteHairSystems(hairSystems)
			else:
				createShave = True
				pfxes = cmds.listConnections(hairSystems[0], t='pfxHair')
				if not pfxes:
					# unknown state
					return script
				pfxes = cmds.listRelatives(pfxes, s=True, f=True)
				def f(x): return cmds.nodeType(cmds.listRelatives(x, s=True, f=True)) == "mesh"
				objs = filter(f, cmds.listConnections(pfxes))
				if objs:
					# there is replacement object
					def f(x): return cmds.nodeType(x)=="shadingEngine"
					shadingGrps = filter(f, cmds.listConnections(cmds.listRelatives(objs, s=True, f=True)))
					[ cmds.delete(cmds.listConnections(x+".surfaceShader")) for x in shadingGrps ]
					cmds.delete(getTopGroups(objs), shadingGrps)
					[ cmds.setAttr(pfx+".visibility", 1) for pfx in pfxes ]
				else:
					if i['polygon'] == "True":
						cmds.select(cmds.listRelatives(pfxes, p=True, f=True), r=True)
						createPolygonHair(deleteHistory=False)
						cmds.select(hairSystems, r=True)
						mel.eval('AttributeEditor')
						createShave = False
				if createShave:
					pfxes = cmds.listConnections(hairSystems, t='pfxHair')
					if not pfxes:
						raise Exception, 'pfxHair not found'
					cmds.select(pfxes, r=True)
					convertPFX2Shave(shavePreset=i['shavePreset'], \
						matchHairCount=bool(i['matchHairCount']),	\
						shaveNodes=i['shaveNodes'],	\
						deleteHistory=True	)
					sh = self.getNodes(master, 'shaveHair')
					if not sh:
						raise Exception, "no shave node created"
					cmds.select(sh, r=True)
					mel.eval('AttributeEditor')
		else:
			if shaveHairs:
				cmds.select(cmds.listRelatives(shaveHairs, p=True, f=True), r=True)
				deleteShaveNodes(deleteInputCurves=True)
			else:
				createHairSystems(i['master'], \
					hairDirection=self.globals['hairDirection'], \
					extract=self.globals['extract'], \
					curveCount=int(i['curveCount']), \
					visibleOnly=bool(self.globals['visibleOnly']), \
					hairSystemPreset=i['hairSystemPreset'])
				hs = self.getNodes(master, 'hairSystem')
				if not hs:
					raise Exception, "no hairsystem created"
				cmds.select(hs, r=True)
				mel.eval('AttributeEditor')

	
	def	generateScript(self):

		def validName(s): return s.replace('|','').replace(':','')
	
		def	delimited(s): return "["+s+"]"
		if not self.layers:
			raise Exception, "missing layers"

		script  = "import traceback, sys\nimport maya.cmds as cmds\n\n"
		script += "turnOffUndo = "+self.globals['turnOffUndo']+"\n"
		script += "hairDirection = '"+self.globals['hairDirection']+"'\n"
		script += "extract = '"+self.globals['extract']+"'\n"
		script += "visibleOnly = "+self.globals['visibleOnly']+"\n"
		script += "shaveGlobalsPreset = '"+self.globals['shaveGlobalsPreset']+"'\n"
		script += "renderLayer = '"+self.globals['renderLayer']+"'\n"
		script += "renderLayerShadow = '"+self.globals['renderLayerShadow']+"'\n"
		script += "passiveCollider = '"+self.globals['passiveCollider']+"'\n"
		script += "deleteHistory = "+self.globals['deleteHistory']+"\n"

		script += "\n\n"

		script += "undoState = cmds.undoInfo(q=True, state=True)\n"
		script += "if turnOffUndo: cmds.undoInfo(state=False)\n\n"
		script += "try:\n\n"

		for l in self.layers:
			if l['nCloth'] == "True":
				script += "\tif cmds.objExists(passiveCollider):\n"
				script += "\t\tjc.hair.createNClothWrapDeformer('"+l['master']+"', "
				if l['patches']:
					script += "'"+"', '".join(l['patches'])+"', "
				script += "passiveCollider, "
				script += "hairDirection=hairDirection, "
				script += "nClothPreset='"+l['nClothPreset']+"'"
				script += ")\n"
				script += "\telse:\n"
				script += "\t\tcmds.warning('nCloth node is not generated because Passive Collider is not specified.')\n"
			if l['shave'] == "True" or l['polygon'] == "True":
				script += "\tjc.hair.createHairs('"+l['master']+"', "
				if l['patches']:
					script += "'"+"', '".join(l['patches'])+"', "
				script += "hairDirection=hairDirection, "
				script += "extract=extract, "
				script += "curveCount="+l['curveCount']+", "
				script += "visibleOnly=visibleOnly, "
				script += "matchHairCount="+l['matchHairCount']+", "
				script += "shaveNodes='"+l['shaveNodes']+"', "
				script += "hairSystemPreset='"+l['hairSystemPreset']+"', "
				script += "shavePreset='"+l['shavePreset']+"', "
				script += "shaveGlobalsPreset=shaveGlobalsPreset, "
				script += "shave="+l['shave']+", "
				script += "polygon="+l['polygon']+", "
				script += "renderLayer=renderLayer, "
				script += "renderLayerShadow=renderLayerShadow, "
				script += "deleteHistory=deleteHistory"
				script += ")\n"

		script += "\n"

		#script += "except:\n\ttraceback.print_exc(limit=2, file=sys.stderr)\n"
		script += "finally:\n\tif turnOffUndo: cmds.undoInfo(state=undoState)\n"

		return script


	def	parseCSV(self, fileObj):
		bool = re.compile("y|true|1", re.I)
		reader = csv.reader(fileObj)
		try:
			for row in reader:
				if row[0].lower().startswith("#layer") and len(row) == 12 and row[1]:
					l = self.newItem(row[1])
					if row[2]: l['patches'] = re.split("\s*", row[2].strip())
					if row[3]: l['curveCount'] = row[3]
					if row[4]: l['hairSystemPreset'] = row[4]
					if row[5]: l['shavePreset'] = row[5]
					if row[6]: l['nClothPreset'] = row[6]
					if row[7]: l['shaveNodes'] = row[7]
					if row[8]: l['matchHairCount'] = str(bool.search(row[8]) != None)
					if row[9]: l['shave'] = str(bool.search(row[9]) != None)
					if row[10]: l['polygon'] = str(bool.search(row[10]) != None)
					if row[11]: l['nCloth'] = str(bool.search(row[11]) != None)
				elif row[0].lower().startswith("#global") and len(row) == 10:
					if row[1]: self.globals['turnOffUndo'] = str(bool.search(row[1]) != None)
					if row[2]: self.globals['hairDirection'] = row[2]
					if row[3]: self.globals['extract'] = row[3]
					if row[4]: self.globals['visibleOnly'] = str(bool.search(row[4]) != None)
					if row[5]: self.globals['shaveGlobalsPreset'] = row[5]
					if row[6]: self.globals['renderLayer'] = row[6]
					if row[7]: self.globals['renderLayerShadow'] = row[7]
					if row[8]: self.globals['passiveCollider'] = row[8]
					if row[9]: self.globals['deleteHistory'] = row[9]
		except csv.Error, e:
		    raise Exception, 'line %d: %s' % (reader.line_num, e)


	def	generateCSV(self, fileObj):
		def concatenate(x,y): return x+" "+y
		writer = csv.writer(fileObj)
		for l in self.layers:
			row = [ "#Layer", l['master'], \
				reduce(concatenate, l['patches']+[""])[:-1],	\
				l['curveCount'], l['hairSystemPreset'], l['shavePreset'], l['nClothPreset'], \
				l['shaveNodes'], l['matchHairCount'], l['shave'], l['polygon'], l['nCloth'] ]
			writer.writerow(row)
		row = [ "#Globals", self.globals['turnOffUndo'], self.globals['hairDirection'],	\
			self.globals['extract'], self.globals['visibleOnly'],	\
			self.globals['shaveGlobalsPreset'],	self.globals['renderLayer'], self.globals['renderLayerShadow'], \
			self.globals['passiveCollider'], self.globals['deleteHistory'] ]
		writer.writerow(row)


	def	destroy(self):
		# DEBUG: should obey 'shave' flag
		for layer in self.layers:
			if cmds.pluginInfo('shaveNode',q=True,l=True):
				shaveNodes = self.getNodes(layer['master'], 'shaveHair')
				if shaveNodes:
					cmds.select(cmds.listRelatives(shaveNodes, p=True, f=True), r=True)
					deleteShaveNodes(deleteInputCurves=True)
			hairSystems = self.getNodes(layer['master'], 'hairSystem')
			if hairSystems:
				pfxes = cmds.ls(cmds.listHistory(hairSystems, f=True), l=True, type='pfxHair')
				if pfxes:
					# delete polygon hair
					meshes = cmds.ls(cmds.listHistory(pfxes, f=True, lv=1), l=True, type='mesh')
					if meshes:
						cmds.delete(getTopGroups(meshes))
				deleteHairSystems(hairSystems)

			# delete ncloth
			wrap = cmds.listConnections(layer['master']+".create")
			if wrap and cmds.nodeType(wrap) == "wrap":
				geom = cmds.listConnections(wrap[0]+".driverPoints[0]")
				base = cmds.listConnections(wrap[0]+".basePoints[0]")
				cmds.delete(layer['master'], ch=True)
				cmds.delete(layer['patches'], ch=True)
				# remove nconstraint
				ncloth = cmds.ls(cmds.listHistory(geom), l=True, type='nCloth')
				if ncloth:
					for map in [".rigidityMap", ".deformMap", ".dampMap", ".massMap", ".collideStrengthMap"]:
						if cmds.attributeQuery(map[1:], typ='nCloth', ex=True):
							ramp = cmds.listConnections(ncloth[0]+map)
							if ramp:
								cmds.delete(ramp)
					constraint = cmds.ls(cmds.listHistory(ncloth, f=True), l=True, type='dynamicConstraint')
					if constraint:
						component = list(set(cmds.ls(cmds.listHistory(ncloth, f=True), type='nComponent')) & set(cmds.ls(cmds.listHistory(constraint), type='nComponent')))
						if component:
							for map in [".strengthMap", ".glueStrengthMap"]:
								ramp = cmds.listConnections(component[0]+map)
								if ramp:
									cmds.delete(ramp)
						cmds.select(cmds.listRelatives(constraint, p=True, f=True), r=True)
						mel.eval('removeDynamicConstraint "selected"')
				cmds.select(geom, r=True)
				mel.eval('removeNCloth "selected"')
				cmds.delete(geom, base)


class	hairstyleBuilderClass:

	__moduleName = ""
	__window = ""
	__gShelfTopLevel = ""
	__hairstyle = None
	__globalsLayout = ""
	__layerListLayout = ""
	__currentTextScrollList = ""
	__saveWindow = ""


	def	__init__(self, moduleName):
		self.__moduleName = moduleName
		self.__window = self.__moduleName.replace('.','_')+"_hairstyleBuilderWindow"
		self.__gShelfTopLevel = mel.eval("$tempVar=$gShelfTopLevel")
		self.__hairstyle = None
		self.__globalsLayout = ""
		self.__layerListLayout = ""
		self.__currentTextScrollList = ""
		self.__saveWindow = self.__moduleName.replace('.','_')+"_hairstyleBuilderSaveWindow"


	def	open(self, hairstyleName=None):
		self.__hairstyle = hairstyle(self.__moduleName)

		for x in self.__hairstyle.globals.keys():
			if cmds.optionVar(ex=self.__moduleName+"."+x):
				self.__hairstyle.globals[x] = str(cmds.optionVar(q=self.__moduleName+"."+x))
				if x == 'visibleOnly' or x == 'deleteHistory':
					self.__hairstyle.globals[x] = str(cmds.optionVar(q=self.__moduleName+"."+x)==1)
			elif cmds.optionVar(ex=self.__moduleName+".hairstyleBuilder."+x):
				self.__hairstyle.globals[x] = str(cmds.optionVar(q=self.__moduleName+".hairstyleBuilder."+x))
				if x == 'turnOffUndo':
					self.__hairstyle.globals[x] = str(cmds.optionVar(q=self.__moduleName+".hairstyleBuilder."+x)==1)

		if not hairstyleName or (hairstyleName and hairstyleName == hairstyleOptions()[0]):
			hairstyleName = ""

		if hairstyleName:
			currentTab = cmds.tabLayout(self.__gShelfTopLevel, q=True, st=True)
			cmds.setParent(currentTab)
			if cmds.shelfLayout(currentTab, q=True, ca=True):
				for b in cmds.shelfLayout(currentTab, q=True, ca=True):
					if cmds.shelfButton(b, q=True, ex=True):
						if hairstyleName == cmds.shelfButton(b, q=True, l=True):
							class hairstyleCSV:
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
							self.__hairstyle.parseCSV(hairstyleCSV(cmds.shelfButton(b, q=True, c=True)))


	def	showWindow(self, hairstyleName=None):
		if cmds.window(self.__window, q=True, ex=True):
			cmds.showWindow(self.__window)
			return

		if not hairstyleName or (hairstyleName and hairstyleName == hairstyleOptions()[0]):
			hairstyleName = ""

		self.open(hairstyleName)

		w = cmds.window(self.__window, t="Hairstyle Builder", w=360, h=630, mb=True)
	
		fl = cmds.formLayout()
		tl = cmds.tabLayout(imw=2, imh=2, cr=True)
		cmds.formLayout(fl, e=True, af=[(tl, "top", 5), (tl, "bottom", 0), (tl, "left", 0), (tl, "right", 0)])
		fl = cmds.formLayout(p=tl)
		cmds.tabLayout(tl, e=True, tli=[1, "Layers"])

		self.__LayerListLayout = fl
		self.showLayers()

		cl = cmds.columnLayout(p=tl, adj=True, co=["both", 10])
		cmds.tabLayout(tl, e=True, tli=[2, "Globals"])

		self.__globalsLayout = cl
		self.showGlobals(hairstyleName)

		jc.menu.destroyMenu(self.__window+"|File")
		m = jc.menu.createMenu(self.__window+"|File", w)
		#jc.menu.commandItem(m, self.__moduleName+".hairstyleBuilderCallback(method='save', hairstyle='"+hairstyleName+"')", "Save")
		#jc.menu.dividerItem(m)
		jc.menu.commandItem(m, self.__moduleName+".hairstyleBuilderCallback(method='importCSV')", "Import")
		jc.menu.commandItem(m, self.__moduleName+".hairstyleBuilderCallback(method='exportCSV')", "Export")

		jc.menu.destroyMenu(self.__window+"|Edit")
		m = jc.menu.createMenu(self.__window+"|Edit", w)
		jc.menu.commandItem(m, self.__moduleName+".hairstyleBuilderCallback(method='saveSettings')", "Save Settings")
		jc.menu.commandItem(m, self.__moduleName+".hairstyleBuilderCallback(method='resetSettings')", "Reset Settings")

		if cmds.about(os=True).startswith("linux"):
			cmds.tabLayout(tl, e=True, cc=self.__moduleName+".hairstyleBuilderCallback(method='changeTab', tabLayout='"+tl+"')")

		cmds.showWindow(self.__window)


	def	showGlobals(self, hairstyleName=None):
		cl = self.__globalsLayout
		cmds.setParent(cl)
		firstColWidth = 120

		cb1 = cmds.checkBoxGrp("turnOffUndo", l="Turn Off Undo:", ncb=1, v1=self.__hairstyle.globals['turnOffUndo']=="True", cl2=["left","left"], ct2=["left","left"], co2=[0,0], h=25, cw2=[firstColWidth,20], cc=self.__moduleName+".hairstyleBuilderCallback(method='updateGlobals', columnLayout='"+cl+"')")

		rb2 = cmds.radioButtonGrp("hairDirection", l="Hair Direction:", nrb=2, la2=directionOptions(), sl=directionOptions().index(self.__hairstyle.globals['hairDirection'])+1, vr=False, cl3=["left","left","left"], ct3=["left","left","left"], co3=[0,0,0], h=25, cw3=[firstColWidth,80,50], cc=self.__moduleName+".hairstyleBuilderCallback(method='updateGlobals', columnLayout='"+cl+"')")
		cmds.radioButtonGrp(rb2, e=True, rat=[2,"both",5])
		cmds.radioButtonGrp(rb2, e=True, rat=[3,"both",5])

		rb3 = cmds.radioButtonGrp("extract", l="Extract:", nrb=2, la2=extractOptions(), sl=extractOptions().index(self.__hairstyle.globals['extract'])+1, vr=False, cl3=["left","left","left"], ct3=["left","left","left"], co3=[0,0,0], h=25, cw3=[firstColWidth,80,50], cc=self.__moduleName+".hairstyleBuilderCallback(method='updateGlobals', columnLayout='"+cl+"')")
		cmds.radioButtonGrp(rb3, e=True, rat=[2,"both",5])
		cmds.radioButtonGrp(rb3, e=True, rat=[3,"both",5])

		cb4 = cmds.checkBoxGrp("visibleOnly", l="Visible Only:", ncb=1, v1=self.__hairstyle.globals['visibleOnly']=="True", cl2=["left","left"], ct2=["left","left"], co2=[0,0], h=25, cw2=[firstColWidth,20], cc=self.__moduleName+".hairstyleBuilderCallback(method='updateGlobals', columnLayout='"+cl+"')")

		fl = cmds.formLayout(p=cl)
		tfg = cmds.textFieldGrp("shaveGlobalsPreset", l='Shave Globals Preset', h=25, ed=False, tx=self.__hairstyle.globals['shaveGlobalsPreset'], w=250, cw2=[firstColWidth,50], co2=[0,0], ct2=["left","left"], cl2=["left","left"])
		b = cmds.button(l="Presets", h=25, w=80)
		pm = cmds.popupMenu(b=1)
		cmds.popupMenu(pm, e=True, pmc=self.__moduleName+".hairstyleBuilderCallback(method='changePreset', textFieldGrp='"+tfg+"', popupMenu='"+pm+"')")
		cmds.formLayout(fl, e=True, af=[(tfg, "top", 7), (tfg, "left", 0)], an=[(tfg, "bottom"), (tfg, "right")])
		cmds.formLayout(fl, e=True, af=[(b, "top", 7)], ac=[(b, "left", 5, tfg)], an=[(b, "bottom"), (b, "right")])

		fl = cmds.formLayout(p=cl)
		tfg = cmds.textFieldGrp("renderLayer", l='Render Layer (Hair)', h=25, ed=False, tx=self.__hairstyle.globals['renderLayer'], w=250, cw2=[firstColWidth,50], co2=[0,0], ct2=["left","left"], cl2=["left","left"])
		b = cmds.button(l="Render Layers", h=25, w=80)
		pm = cmds.popupMenu(b=1)
		cmds.popupMenu(pm, e=True, pmc=self.__moduleName+".hairstyleBuilderCallback(method='changePreset', textFieldGrp='"+tfg+"', popupMenu='"+pm+"')")
		cmds.formLayout(fl, e=True, af=[(tfg, "top", 7), (tfg, "left", 0)], an=[(tfg, "bottom"), (tfg, "right")])
		cmds.formLayout(fl, e=True, af=[(b, "top", 7)], ac=[(b, "left", 5, tfg)], an=[(b, "bottom"), (b, "right")])

		fl = cmds.formLayout(p=cl)
		tfg = cmds.textFieldGrp("renderLayerShadow", l='Render Layer (Shadow)', h=25, ed=False, tx=self.__hairstyle.globals['renderLayerShadow'], w=250, cw2=[firstColWidth,50], co2=[0,0], ct2=["left","left"], cl2=["left","left"])
		b = cmds.button(l="Render Layers", h=25, w=80)
		pm = cmds.popupMenu(b=1)
		cmds.popupMenu(pm, e=True, pmc=self.__moduleName+".hairstyleBuilderCallback(method='changePreset', textFieldGrp='"+tfg+"', popupMenu='"+pm+"')")
		cmds.formLayout(fl, e=True, af=[(tfg, "top", 7), (tfg, "left", 0)], an=[(tfg, "bottom"), (tfg, "right")])
		cmds.formLayout(fl, e=True, af=[(b, "top", 7)], ac=[(b, "left", 5, tfg)], an=[(b, "bottom"), (b, "right")])

		fl = cmds.formLayout(p=cl)
		tfg = cmds.textFieldGrp("passiveCollider", l="Passive Collider:", tx=self.__hairstyle.globals['passiveCollider'], ed=False, w=250, h=25, cw2=[firstColWidth,50], co2=[0,0], ct2=["left","left"], cl2=["left","left"])
		b = cmds.button(l=" << ", h=25, w=80, c=self.__moduleName+".hairstyleBuilderCallback(method='updatePassiveCollider', textFieldGrp='"+tfg+"')")
		cmds.formLayout(fl, e=True, af=[(tfg, "top", 7), (tfg, "left", 0)], an=[(tfg, "bottom"), (tfg, "right")])
		cmds.formLayout(fl, e=True, af=[(b, "top", 7)], ac=[(b, "left", 5, tfg)], an=[(b, "bottom"), (b, "right")])

		cmds.setParent(cl)
		cb9 = cmds.checkBoxGrp("deleteHistory", l="Delete History:", ncb=1, v1=self.__hairstyle.globals['deleteHistory']=="True", cl2=["left","left"], ct2=["left","left"], co2=[0,0], h=25, cw2=[firstColWidth,50], cc=self.__moduleName+".hairstyleBuilderCallback(method='updateGlobals', columnLayout='"+cl+"')")

		fl = cmds.formLayout(p=cl)
		tfg = cmds.textFieldGrp("hairstyle", l="Hairstyle:", tx=hairstyleName, ed=True, h=25, w=250, cw2=[firstColWidth,50], cl2=["left","left"], ct2=["left","left"], co2=[0,0])
		b = cmds.button(l=" Save ", h=25, w=80, c=self.__moduleName+".hairstyleBuilderCallback(method='action', action='save', textFieldGrp='"+tfg+"')")
		cmds.formLayout(fl, e=True, af=[(tfg, "top", 7), (tfg, "left", 0)], an=[(tfg, "bottom"), (tfg, "right")])
		cmds.formLayout(fl, e=True, af=[(b, "top", 7)], ac=[(b, "left", 5, tfg)], an=[(b, "bottom"), (b, "right")])


	def	showLayers(self):
		cmds.setParent(self.__LayerListLayout)
		if cmds.formLayout(self.__LayerListLayout, q=1, ca=1):
			[ cmds.deleteUI(c) for c in cmds.formLayout(self.__LayerListLayout, q=1, ca=1) ]
	
		b = cmds.button(p=self.__LayerListLayout, l="Add Layer", h=30, c=self.__moduleName+".hairstyleBuilderCallback(method='add')")
		sl = cmds.scrollLayout(p=self.__LayerListLayout, cr=True)
		cmds.formLayout(self.__LayerListLayout, e=True, af=[(b, "top", 10), (b, "left", 10), (b, "right", 10)], an=[(b, "bottom")])
		cmds.formLayout(self.__LayerListLayout, e=True, ac=[(sl, "top", 10, b)], af=[(sl, "left", 0), (sl, "right", 0), (sl, "bottom", 0)])

		pl = cmds.columnLayout(adj=True)
		firstColWidth = 90
		tempWidth = 200

		for p in reversed(self.__hairstyle.layers):
			fr = cmds.frameLayout(p=pl, cll=True, l=p['master'], cl=p['frameState'])
			cmds.frameLayout(fr, e=True, cc=self.__moduleName+".hairstyleBuilderCallback(method='collapseFrame', collapse=True, name='"+p['master']+"')")
			cmds.frameLayout(fr, e=True, ec=self.__moduleName+".hairstyleBuilderCallback(method='collapseFrame', collapse=False, name='"+p['master']+"')")
	
			fl = cmds.formLayout(p=fr)
			cl = cmds.columnLayout(adj=True)
			cmds.formLayout(fl, e=True, af=[(cl, "top", 0), (cl, "bottom", 0), (cl, "left", 0), (cl, "right", 0)])

			fl = cmds.formLayout(p=cl, h=25, w=tempWidth)
			tt2 = cmds.text(l="Master:", w=firstColWidth, al="left")
			tsl2 = cmds.textScrollList(nr=1, a=p['master'], w=150, h=20)
			cmds.popupMenu(b=3)
			mi1 = cmds.menuItem(l="Hair System")
			mi2 = cmds.menuItem(l="Shave node")
			b2 = cmds.button(l="Setup", h=25, w=50)
			cmds.button(b2, e=True, c=self.__moduleName+".hairstyleBuilderCallback(method='setup', master='"+p['master']+"', button='"+b2+"')")
			cmds.formLayout(fl, e=True, af=[(tt2, "top", 7), (tt2, "left", 5)], an=[(tt2, "bottom"), (tt2, "right")])
			cmds.formLayout(fl, e=True, af=[(b2, "top", 7), (b2, "right", 5)], an=[(b2, "bottom"), (b2, "left")])
			cmds.formLayout(fl, e=True, af=[(tsl2, "top", 7)], ac=[(tsl2, "left", 0, tt2), (tsl2, "right", 5, b2)], an=[(tsl2, "bottom")])

			fl = cmds.formLayout(p=cl, h=60, w=tempWidth)
			tt3 = cmds.text(l="Patches:", w=firstColWidth, al="left")
			tsl3 = cmds.textScrollList(ams=True, nr=5, a=p['patches'])
			b3a = cmds.button(l="Add", h=25, w=50, c=self.__moduleName+".hairstyleBuilderCallback(method='updatePatches', action='add', textScrollList='"+tsl3+"', master='"+p['master']+"')")
			b3b = cmds.button(l="Remove", h=25, w=50, c=self.__moduleName+".hairstyleBuilderCallback(method='updatePatches', action='remove', textScrollList='"+tsl3+"', master='"+p['master']+"')")
			cmds.formLayout(fl, e=True, af=[(tt3, "top", 7), (tt3, "left", 5)], an=[(tt3, "bottom"), (tt3, "right")])
			cmds.formLayout(fl, e=True, af=[(b3a, "top", 7), (b3a, "right", 5)], an=[(b3a, "bottom"), (b3a, "left")])
			cmds.formLayout(fl, e=True, ac=[(b3b, "top", 5, b3a)], af=[(b3b, "right", 5)], an=[(b3b, "bottom"), (b3b, "left")])
			cmds.formLayout(fl, e=True, af=[(tsl3, "top", 7)], ac=[(tsl3, "left", 0, tt3), (tsl3, "right", 5, b3a)], an=[(tsl3, "bottom")])

			fl = cmds.formLayout(p=cl, w=tempWidth)
			ilg4 = cmds.intSliderGrp(l="Curve Count:", v=int(p['curveCount']), f=True, min=0, max=10, ad3=3, cw3=[firstColWidth, 50, 50], co3=[0,0,0], ct3=["left","left","left"], cl3=["left","left","left"])
			cmds.formLayout(fl, e=True, af=[(ilg4, "top", 7), (ilg4, "left", 5), (ilg4, "right", 5)], an=[(ilg4, "bottom")])

			fl = cmds.formLayout(p=cl, w=tempWidth)
			tfg1 = cmds.textFieldGrp("hairSystemPreset", l='Hair System Preset', h=25, ed=False, tx=p['hairSystemPreset'], ad2=2, cw2=[firstColWidth,50], co2=[0,0], ct2=["left","left"], cl2=["left","left"])
			b = cmds.button(l="Presets", h=25, w=50)
			pm = cmds.popupMenu(b=1)
			cmds.popupMenu(pm, e=True, pmc=self.__moduleName+".hairstyleBuilderCallback(method='changePreset', textFieldGrp='"+tfg1+"', popupMenu='"+pm+"', master='"+p['master']+"')")
			cmds.formLayout(fl, e=True, af=[(b, "top", 7), (b, "right", 5)], an=[(b, "left"), (b, "bottom")])
			cmds.formLayout(fl, e=True, af=[(tfg1, "top", 7), (tfg1, "left", 5)], an=[(tfg1, "bottom")], ac=[(tfg1, "right", 5, b)])

			fl = cmds.formLayout(p=cl, w=tempWidth)
			tfg2 = cmds.textFieldGrp("shavePreset", l='Shave Preset', h=25, ed=False, tx=p['shavePreset'], ad2=2, cw2=[firstColWidth,50], co2=[0,0], ct2=["left","left"], cl2=["left","left"])
			b = cmds.button(l="Presets", h=25, w=50)
			pm = cmds.popupMenu(b=1)
			cmds.popupMenu(pm, e=True, pmc=self.__moduleName+".hairstyleBuilderCallback(method='changePreset', textFieldGrp='"+tfg2+"', popupMenu='"+pm+"', master='"+p['master']+"')")
			cmds.formLayout(fl, e=True, af=[(b, "top", 7), (b, "right", 5)], an=[(b, "left"), (b, "bottom")])
			cmds.formLayout(fl, e=True, af=[(tfg2, "top", 7), (tfg2, "left", 5)], an=[(tfg2, "bottom")], ac=[(tfg2, "right", 5, b)])

			fl = cmds.formLayout(p=cl, w=tempWidth)
			tfg3 = cmds.textFieldGrp("nClothPreset", l='nCloth Preset', h=25, ed=False, tx=p['nClothPreset'], ad2=2, cw2=[firstColWidth,50], co2=[0,0], ct2=["left","left"], cl2=["left","left"])
			b = cmds.button(l="Presets", h=25, w=50)
			pm = cmds.popupMenu(b=1)
			cmds.popupMenu(pm, e=True, pmc=self.__moduleName+".hairstyleBuilderCallback(method='changePreset', textFieldGrp='"+tfg3+"', popupMenu='"+pm+"', master='"+p['master']+"')")
			cmds.formLayout(fl, e=True, af=[(b, "top", 7), (b, "right", 5)], an=[(b, "left"), (b, "bottom")])
			cmds.formLayout(fl, e=True, af=[(tfg3, "top", 7), (tfg3, "left", 5)], an=[(tfg3, "bottom")], ac=[(tfg3, "right", 5, b)])

			fl = cmds.formLayout(p=cl, w=tempWidth)
			rb = cmds.radioButtonGrp("shaveNodes", l="Shave Nodes:", nrb=2, la2=shaveNodesOptions(), sl=shaveNodesOptions().index(p['shaveNodes'])+1, vr=False, cl3=["left","left","left"], ct3=["left","left","left"], co3=[0,0,0], h=25, cw3=[firstColWidth,80,50])
			cmds.radioButtonGrp(rb, e=True, rat=[2,"both",5])
			cmds.radioButtonGrp(rb, e=True, rat=[3,"both",5])
			cmds.formLayout(fl, e=True, af=[(rb, "top", 7), (rb, "left", 5)], an=[(rb, "bottom"), (rb, "right")])

			fl = cmds.formLayout(p=cl, w=tempWidth)
			cb5 = cmds.checkBox("matchHairCount", l="Match Hair Count",  v=p['matchHairCount']=="True", w=110)
			cmds.formLayout(fl, e=True, af=[(cb5, "top", 7), (cb5, "left", 5)], an=[(cb5, "bottom"), (cb5, "right")])

			fl = cmds.formLayout(p=cl, w=tempWidth)
			t = cmds.text(l="Output:", w=firstColWidth, h=25)
			cb6 = cmds.checkBox(l="nCloth", w=60, h=25, v=p['nCloth']=="True")
			cb7 = cmds.checkBox(l="Shave", w=60, h=25, v=p['shave']=="True")
			cb8 = cmds.checkBox(l="Polygon", w=70, h=25, v=p['polygon']=="True")
			cmds.formLayout(fl, e=True, af=[(t, "top", 7), (t, "left", 5)], an=[(t, "bottom"), (t, "right")])
			cmds.formLayout(fl, e=True, af=[(cb6, "top", 7)], ac=[(cb6, "left", 5, t)], an=[(cb6, "bottom"), (cb6, "right")])
			cmds.formLayout(fl, e=True, af=[(cb7, "top", 7)], ac=[(cb7, "left", 5, cb6)], an=[(cb7, "bottom"), (cb7, "right")])
			cmds.formLayout(fl, e=True, af=[(cb8, "top", 7)], ac=[(cb8, "left", 5, cb7)], an=[(cb8, "bottom"), (cb8, "right")])

			fl = cmds.formLayout(p=cl, w=tempWidth)
			b4 = cmds.button(l="Remove", c=self.__moduleName+".hairstyleBuilderCallback(method='remove', textScrollList='"+tsl2+"')")
			cmds.formLayout(fl, e=True, af=[(b4, "left", 5), (b4, "right", 5), (b4, "bottom", 5), (b4, "top", 7)])

			cmds.menuItem(mi1, e=True, c=self.__moduleName+".hairstyleBuilderCallback(method='selectPreset', master='"+p['master']+"', type='hairSystem', textFieldGrp='"+tfg1+"')")
			cmds.menuItem(mi2, e=True, c=self.__moduleName+".hairstyleBuilderCallback(method='selectPreset', master='"+p['master']+"', type='shaveHair', textFieldGrp='"+tfg2+"')")

			cmds.textScrollList(tsl2, e=True, sc=self.__moduleName+".hairstyleBuilderCallback(method='select', textScrollList='"+tsl2+"')")
			cmds.textScrollList(tsl3, e=True, sc=self.__moduleName+".hairstyleBuilderCallback(method='select', textScrollList='"+tsl3+"')")
			cmds.intSliderGrp(ilg4, e=True, cc=self.__moduleName+".hairstyleBuilderCallback(method='changeInt', textScrollList='"+tsl2+"', intSliderGrp='"+ilg4+"')")
			cmds.checkBox(cb5, e=True, cc=self.__moduleName+".hairstyleBuilderCallback(method='changeBool', textScrollList='"+tsl2+"', checkBox='"+cb5+"')")
			cmds.radioButtonGrp(rb, e=True, cc=self.__moduleName+".hairstyleBuilderCallback(method='changeRadio', textScrollList='"+tsl2+"', radioButtonGrp='"+rb+"')")
			cmds.checkBox(cb6, e=True, cc=self.__moduleName+".hairstyleBuilderCallback(method='changeBool', textScrollList='"+tsl2+"', checkBox='"+cb6+"')")
			cmds.checkBox(cb7, e=True, cc=self.__moduleName+".hairstyleBuilderCallback(method='changeBool', textScrollList='"+tsl2+"', checkBox='"+cb7+"')")
			cmds.checkBox(cb8, e=True, cc=self.__moduleName+".hairstyleBuilderCallback(method='changeBool', textScrollList='"+tsl2+"', checkBox='"+cb8+"')")


	def	changeTab(self, **keywords):
		tl = keywords['tabLayout']
		tab = cmds.tabLayout(tl, q=True, sti=True)
		if tab == 2:
			self.showLayers()


	def	collapseFrame(self, **keywords):
		item = self.__hairstyle.getItem(keywords['name'])
		if item:
			item['frameState'] = keywords['collapse']


	def	build(self, hairstyleName=None):
		if not hairstyleName or (hairstyleName and hairstyleName == hairstyleOptions()[0]):
			hairstyleName = ""

		self.open(hairstyleName)
		exec(self.__hairstyle.generateScript())


	#def	save(self, hairstyle):
	#	if cmds.window(self.__saveWindow, q=True, ex=True):
	#		cmds.showWindow(self.__saveWindow)
	#		return
	#	if cmds.windowPref(self.__saveWindow, ex=True):
	#		cmds.windowPref(self.__saveWindow, r=True)
	#	totalWidth = 360
	#	w = cmds.window(self.__saveWindow, t="Save Hairstyle", w=totalWidth, h=140, mb=False)
	#	cmds.columnLayout(w=totalWidth)
	#	tfg = cmds.textFieldGrp(l='Hairstyle', tx=hairstyle, w=totalWidth, h=25, cw2=[100,200])
	#	cmds.text(l="", h=50)
	#	cmds.rowLayout(nc=2, w=totalWidth, h=25, cw2=[totalWidth/2,totalWidth/2], ct2=['both','both'], cl2=['center','center'])
	#	cmds.button(l='Save', h=25, c=self.__moduleName+".hairstyleBuilderCallback(method='action', action='save', textFieldGrp='"+tfg+"', window='"+w+"')")
	#	cmds.button(l='Cancel', h=25, c=self.__moduleName+".hairstyleBuilderCallback(method='action', action='cancel', window='"+w+"')")
	#	cmds.showWindow()


	def	importCSV(self):
		self.__hairstyle = hairstyle(self.__moduleName)
		f = cmds.fileDialog(m=0)
		if f:
			file = open(f, "rb")
			self.__hairstyle.parseCSV(file)
			file.close()
			self.showLayers()
			self.updateGlobalsUI()


	def	exportCSV(self):
		f = cmds.fileDialog(m=1)
		if f:
			file = open(f, "wb")
			self.__hairstyle.generateCSV(file)
			file.close()


	def	saveSettings(self):
		cmds.optionVar(sv=(self.__moduleName+".hairstyleBuilder.hairstyle", self.__hairstyle.globals['hairstyle']))
		cmds.optionVar(iv=(self.__moduleName+".hairstyleBuilder.turnOffUndo", self.__hairstyle.globals['turnOffUndo']=="True"))
		cmds.optionVar(sv=(self.__moduleName+".hairDirection", self.__hairstyle.globals['hairDirection']))
		cmds.optionVar(sv=(self.__moduleName+".extract", self.__hairstyle.globals['extract']))
		cmds.optionVar(iv=(self.__moduleName+".visibleOnly", self.__hairstyle.globals['visibleOnly']=="True"))
		cmds.optionVar(sv=(self.__moduleName+".shaveGlobalsPreset", self.__hairstyle.globals['shaveGlobalsPreset']))
		cmds.optionVar(sv=(self.__moduleName+".renderLayer", self.__hairstyle.globals['renderLayer']))
		cmds.optionVar(sv=(self.__moduleName+".renderLayerShadow", self.__hairstyle.globals['renderLayerShadow']))
		cmds.optionVar(iv=(self.__moduleName+".deleteHistory", self.__hairstyle.globals['deleteHistory']=="True"))


	def	resetSettings(self):
		temp = hairstyle(self.__moduleName)
		self.__hairstyle.globals = temp.globals
		self.saveSettings()
		self.updateGlobalsUI()


	def	destroy(self, hairstyle):
		if hairstyle not in hairstyleOptions()[1:]:
			raise Exception, "hairstyle does not exist"
		self.open(hairstyle)
		self.__hairstyle.destroy()


	def	updateGlobalsUI(self):
		cl = self.__globalsLayout
		for c in cmds.columnLayout(cl, q=True, ca=True):
			if 'formLayout' in c:
				for cc in cmds.formLayout(c, q=True, ca=True):
					if cc.find('shaveGlobalsPreset') > -1:
						cmds.textFieldGrp(cl+"|"+c+"|"+cc, e=True, tx=self.__hairstyle.globals['shaveGlobalsPreset'])
					elif cc.find('renderLayer') > -1:
						cmds.textFieldGrp(cl+"|"+c+"|"+cc, e=True, tx=self.__hairstyle.globals['renderLayer'])
					elif cc.find('renderLayerShadow') > -1:
						cmds.textFieldGrp(cl+"|"+c+"|"+cc, e=True, tx=self.__hairstyle.globals['renderLayerShadow'])
					elif cc.find('passiveCollider') > -1:
						cmds.textFieldGrp(cl+"|"+c+"|"+cc, e=True, tx=self.__hairstyle.globals['passiveCollider'])
			elif c.find('turnOffUndo') > -1:
				cmds.checkBoxGrp(cl+"|"+c, e=True, v1=self.__hairstyle.globals['turnOffUndo']=="True")
			elif c.find('hairDirection') > -1:
				cmds.radioButtonGrp(cl+"|"+c, e=True, sl=directionOptions().index(self.__hairstyle.globals['hairDirection'])+1)
			elif c.find('extract') > -1:
				cmds.radioButtonGrp(cl+"|"+c, e=True, sl=extractOptions().index(self.__hairstyle.globals['extract'])+1)
			elif c.find('visibleOnly') > -1:
				cmds.checkBoxGrp(cl+"|"+c, e=True, v1=self.__hairstyle.globals['visibleOnly']=="True")
			elif c.find('deleteHistory') > -1:
				cmds.checkBoxGrp(cl+"|"+c, e=True, v1=self.__hairstyle.globals['deleteHistory']=="True")
			#elif c.find('hairstyle') > -1:
			#	cmds.textFieldGrp(cl+"|"+c, e=True, tx=self.__hairstyle.globals[c])


	def	updateGlobals(self, **keywords):
		cl = keywords['columnLayout']
		for i in self.__hairstyle.globals.keys():
			if "turnOffUndo" in i or "visibleOnly" in i or "deleteHistory" in i:
				self.__hairstyle.globals[i] = str(cmds.checkBoxGrp(cl+"|"+i, q=True, v1=True)==1)
			elif "hairDirection" in i:
				self.__hairstyle.globals[i] = directionOptions()[cmds.radioButtonGrp(cl+"|"+i, q=True, sl=True)-1]
			elif "extract" in i:
				self.__hairstyle.globals[i] = extractOptions()[cmds.radioButtonGrp(cl+"|"+i, q=True, sl=True)-1]


	def	action(self, **keywords):
		action = keywords['action']


		tfg = keywords['textFieldGrp']

		name = cmds.textFieldGrp(tfg, q=True, tx=True)
		if not name:
			raise Exception, "missing hairstyle name"

		if action == 'save':
			self.__hairstyle.globals['hairstyle'] = name
			self.saveSettings()
	
			class temp:
				buffer = ""
				def	__init__(self):
					self.buffer = ""
				def	write(self, content):
					self.buffer += content
				def writerow(self, content):
					self.buffer += content + "\n"
			tempfile = temp()
	
			self.__hairstyle.generateCSV(tempfile)
	
			currentTab = cmds.tabLayout(self.__gShelfTopLevel, q=True, st=True)
			cmds.setParent(currentTab)
	
			tempfile.buffer += "jc.hair.buildHairstyle('"+name+"')"
			if cmds.shelfLayout(currentTab, q=True, ca=True):
				for b in cmds.shelfLayout(currentTab, q=True, ca=True):
					if cmds.shelfButton(b, q=True, ex=True):
						if name == cmds.shelfButton(b, q=True, l=True):
							cmds.shelfButton(b, e=True, c=tempfile.buffer.strip().replace("\r\n","\r"))
							cmds.deleteUI(self.__window)
							#cmds.deleteUI(keywords['window'])
							return
	
			mel.eval("scriptToShelf \""+name+"\" \""+tempfile.buffer.strip().replace("\r\n","\\r").replace("\"","\\\"")+"\" \"0\"")
			cmds.deleteUI(self.__window)
			#cmds.deleteUI(keywords['window'])


	def	add(self, **keywords):
		self.__hairstyle.addItem(cmds.ls(sl=True))
		self.showLayers()


	def	selectPreset(self, **keywords):
		master = keywords['master']
		tfg = keywords['textFieldGrp']
		preset = cmds.textFieldGrp(tfg, q=True, tx=True)
		nodes = cmds.listRelatives(master, ad=True, f=True, typ=keywords['type'])
		if nodes:
			for n in nodes:
				if n.split('|')[-1].startswith(preset):
					cmds.select(n, r=True)
					break

	def	select(self, **keywords):
		tsl = keywords['textScrollList']
		if self.__currentTextScrollList and self.__currentTextScrollList != tsl and cmds.textScrollList(self.__currentTextScrollList, q=True, ex=True):
			cmds.textScrollList(self.__currentTextScrollList, e=True, da=True)
		items = cmds.textScrollList(tsl, q=True, si=True)
		if items:
			def f(x): return cmds.objExists(x)
			cmds.select(filter(f, items), r=True)
			self.__currentTextScrollList = tsl


	def	updatePassiveCollider(self, **keywords):
		tfg = keywords['textFieldGrp']
		for s in cmds.ls(sl=True):
			if cmds.ls(cmds.listHistory(s, f=True), type='nRigid'):
				cmds.textFieldGrp(tfg, e=True, tx=s)
				self.__hairstyle.globals['passiveCollider'] = s


	def	changeInt(self, **keywords):
		tsl = keywords['textScrollList']
		ilg = keywords['intSliderGrp']
		if not cmds.textScrollList(tsl, q=True, ai=True):
			raise Exception, "master empty"
		item = self.__hairstyle.getItem(cmds.textScrollList(tsl, q=True, ai=True)[0])
		item['curveCount'] = str(cmds.intSliderGrp(ilg, q=True, v=True))


	def	changeBool(self, **keywords):
		tsl = keywords['textScrollList']
		cb = keywords['checkBox']
		if not cmds.textScrollList(tsl, q=True, ai=True):
			raise Exception, "master empty"
		name = cmds.textScrollList(tsl, q=True, ai=True)[0]
		item = self.__hairstyle.getItem(name)
		label = cmds.checkBox(cb, q=True, l=True)
		label = label.strip().replace(' ','')
		label = label[0].lower() + label[1:]
		item[label] = str(cmds.checkBox(cb, q=True, v=True) == 1)


	def	changeRadio(self, **keywords):
		tsl = keywords['textScrollList']
		rb = keywords['radioButtonGrp']
		if not cmds.textScrollList(tsl, q=True, ai=True):
			raise Exception, "master empty"
		item = self.__hairstyle.getItem(cmds.textScrollList(tsl, q=True, ai=True)[0])
		item[rb.split('|')[-1]] = shaveNodesOptions()[cmds.radioButtonGrp(rb, q=True, sl=True)-1]


	def	changePreset(self, **keywords):
		tfg = keywords['textFieldGrp']
		type = tfg.split('|')[-1]
		if 'popupMenu' in keywords:
			pm = keywords['popupMenu']
			if type == "hairSystemPreset":
				l = getHairSystemPresetsCallback()
			elif type == "shavePreset":
				l = getShaveHairPresetsCallback()
			elif type == "nClothPreset":
				l = getNClothPresetsCallback()
			elif type == "shaveGlobalsPreset":
				l = getShaveGlobalsPresetsCallback()
			elif "renderLayer" in type:
				l = getRenderLayersCallback()
			cmds.popupMenu(pm, e=True, dai=True)
			for i in l:
				m = cmds.menuItem(l=i, p=pm)
				if 'master' in keywords:
					cmds.menuItem(m, e=True, c=self.__moduleName+".hairstyleBuilderCallback(method='changePreset', textFieldGrp='"+tfg+"', menuItem='"+m+"', type='"+type+"', master='"+keywords['master']+"')")
				else:
					cmds.menuItem(m, e=True, c=self.__moduleName+".hairstyleBuilderCallback(method='changePreset', textFieldGrp='"+tfg+"', menuItem='"+m+"', type='"+type+"')")
		elif 'menuItem' in keywords:
			value = cmds.menuItem(keywords['menuItem'], q=True, l=True)
			cmds.textFieldGrp(tfg, e=True, tx=value)
			if type == "shaveGlobalsPreset" or "renderLayer" in type:
				self.__hairstyle.globals[type] = value
			else:
				i = self.__hairstyle.getItem(keywords['master'])
				if i:
					i[type] = value


	def	setup(self, **keywords):
		self.__hairstyle.testMaster(keywords['master'])


	def	updatePatches(self, **keywords):
		action = keywords['action']
		tsl = keywords['textScrollList']
		master = keywords['master']
		items = cmds.textScrollList(tsl, q=True, ai=True)
		if not items: items = []
		if action == 'remove':
			selection = []
			if cmds.ls(sl=True) and cmds.listRelatives(s=True, type='nurbsSurface'):
				selection = cmds.listRelatives(cmds.listRelatives(s=True, type='nurbsSurface', f=True), p=True)
			if cmds.textScrollList(tsl, q=True, si=True):
				selection += cmds.textScrollList(tsl, q=True, si=True)
			for i in list(set(selection)&set(items)):
				cmds.textScrollList(tsl, e=True, ri=i)
		else:
			if not cmds.ls(sl=True) or not cmds.listRelatives(s=True, type='nurbsSurface'):
				raise Exception, "no valid selection"
			selection = cmds.listRelatives(cmds.listRelatives(s=True, type='nurbsSurface', f=True), p=True)
			for i in list(set(selection)-set(items)-set([master])):
				cmds.textScrollList(tsl, e=True, ap=[1,i])
		i = self.__hairstyle.getItem(master)
		if i:
			i['patches'] = cmds.textScrollList(tsl, q=True, ai=True)
			if not i['patches']:
				i['patches'] = []


	def	remove(self, **keywords):
		tsl = keywords['textScrollList']
		if not cmds.textScrollList(tsl, q=True, ai=True):
			raise Exception, "master empty"
		self.__hairstyle.removeItem(cmds.textScrollList(tsl, q=True, ai=True)[0])
		self.showLayers()


	def	callback(self, **keywords):
		a = "self."+keywords['method']+"("
		for (n,v) in keywords.iteritems():
			if n != 'method':
				a += ", "+n+"='"+str(v)+"'"
		eval(a.replace(', ','',1)+")")


##	end of hairstyleBuilderClass	##

# global variables
__hairstyleBuilder = None
__hairstyleBuilderCallback = None


def	hairstyleBuilderCallback(*args, **keywords):
	__hairstyleBuilderCallback(*args, **keywords)


def	hairstyleBuilder(hairstyle=None):

	# as assignment statements would make variables local implicitly, this global statement is necessary
	global __hairstyleBuilder, __hairstyleBuilderCallback

	if not __hairstyleBuilder:
		__hairstyleBuilder = hairstyleBuilderClass(__moduleName)
		__hairstyleBuilderCallback = __hairstyleBuilder.callback

	__hairstyleBuilder.showWindow(hairstyle)


def	buildHairstyle(hairstyle=None):

	# as assignment statements would make variables local implicitly, this global statement is necessary
	global __hairstyleBuilder, __hairstyleBuilderCallback

	if not __hairstyleBuilder:
		__hairstyleBuilder = hairstyleBuilderClass(__moduleName)
		__hairstyleBuilderCallback = __hairstyleBuilder.callback

	__hairstyleBuilder.build(hairstyle)


def	hairstyleOptions2():
	p = []
	currentTab = cmds.tabLayout(mel.eval("$tempVar=$gShelfTopLevel"), q=True, st=True)
	if cmds.shelfLayout(currentTab, q=True, ca=True):
		for b in cmds.shelfLayout(currentTab, q=True, ca=True):
			if cmds.shelfButton(b, q=True, ex=True):
				if cmds.shelfButton(b, q=True, c=True).lower().startswith("#layer"):
					p.append(cmds.shelfButton(b, q=True, l=True))
	return p


def	hairstyleOptions1():
	return [ "None" ] + hairstyleOptions2()


def	hairstyleOptions():
	return [ "Create New" ] + hairstyleOptions2()


def	batchRender(**keywords):

	if not cmds.file(q=True, sn=True):
		raise Exception, "scene must be saved"

	required = set(['camera', 'renderLayer'])
	
	if set(keywords.keys()) & required != required:
		raise Exception, "argument error"
		
	camera = keywords['camera']
	renderLayer = keywords['renderLayer']
	startNow = True
	saveScene = True
	shutdown = False
	if 'startNow' in keywords.keys(): startNow = keywords['startNow']
	if 'saveScene' in keywords.keys(): saveScene = keywords['saveScene']
	if 'shutdown' in keywords.keys(): shutdown = keywords['shutdown']
	
	startFrame = None
	endFrame = None
	if 'startFrame' in keywords.keys(): startFrame = keywords['startFrame']
	if 'endFrame' in keywords.keys(): endFrame = keywords['endFrame']
	if startFrame != None and endFrame != None and startFrame > endFrame:
		raise Exception, "argument Error: startFrame > endFrame"

	render = os.path.join(os.path.abspath(os.getenv('MAYA_LOCATION')), "bin")
	if cmds.about(nt=True):
		render = os.path.join(render, "render.exe")
	else:
		render = os.path.join(render, "Render")

	projectDirectory = cmds.workspace(q=True, rd=True)

	currentScene = os.path.abspath(cmds.file(q=True, sn=True))

	batchCmdPath = projectDirectory
	if 'scene' in cmds.workspace(q=True, frl=True):
		scene = cmds.file(q=True, sn=True, shn=True).replace('.', '_')
		batchCmdPath = os.path.join(projectDirectory, cmds.workspace(fre='scene'), scene+'_'+renderLayer)
	if cmds.about(nt=True):
		batchCmdPath += ".bat"

	quote = ""
	if cmds.about(nt=True):
		quote = '"'
	batchCmd  = ""
	if cmds.about(nt=True):
		batchCmd += "echo off\n"
		batchCmd += "set render="+quote+render+quote+"\n"
		batchCmd += "set proj="+quote+projectDirectory+quote+"\n"
		batchCmd += "set scene="+quote+currentScene+quote+"\n"
		batchCmd += "set camera="+quote+camera+quote+"\n"
		if renderLayer != None and renderLayer != "None":
			batchCmd += "set layer="+quote+renderLayer+quote+"\n"
		batchCmd += "set MI_MAYA_BATCH_OPTIONS="+quote+"NumThreadAuto=1;MemLimitAuto=1;LogVerbosity=5"+quote+"\n"
		batchCmd += "echo on\n"
		if startFrame != None and endFrame != None and endFrame >= startFrame:
			batchCmd += "%%render%% -r mr -proj %%proj%% -cam %%camera%% -s %d -e %d" % (startFrame, endFrame)
		else:
			batchCmd += "%render% -r mr -proj %proj% -cam %camera%"
		if renderLayer != None and renderLayer != "None":
			batchCmd += " -rl %layer%"
		batchCmd += " %scene%\n"
	else:
		batchCmd += "render="+quote+render+quote+"\n"
		batchCmd += "proj="+quote+projectDirectory+quote+"\n"
		batchCmd += "scene="+quote+currentScene+quote+"\n"
		batchCmd += "camera="+quote+camera+quote+"\n"
		if renderLayer != None and renderLayer != "None":
			batchCmd += "layer="+quote+renderLayer+quote+"\n"
		batchCmd += "export MI_MAYA_BATCH_OPTIONS="+quote+"NumThreadAuto=1;MemLimitAuto=1;LogVerbosity=5"+quote+"\n"
		if startFrame != None and endFrame != None and endFrame >= startFrame:
			batchCmd += "$render -r mr -proj $proj -cam $camera -s %d -e %d" % (startFrame, endFrame)
		else:
			batchCmd += "$render -r mr -proj $proj -cam $camera"
		if renderLayer != None and renderLayer != "None":
			batchCmd += " -rl $layer"
		batchCmd += " $scene\n"

	if shutdown:
		if cmds.about(nt=True):
			batchCmd += "shutdown -s"
		else:
			batchCmd += "shutdown -P 0"

	# save file
	file = open(batchCmdPath, "w+")
	if not cmds.about(nt=True):
		file.write("#!/bin/bash\n")
	file.write(batchCmd)
	file.close()
	if not cmds.about(nt=True):
		os.chmod(batchCmdPath, 511)

	# check paths existence
	if not os.path.exists(render):
		raise Exception, "missing file "+render
	if not os.path.exists(batchCmdPath):
		raise Exception, "missing file "+batchCmdPath
	if not os.path.exists(currentScene):
		raise Exception, "missing file "+currentScene

	print "batch file: "+batchCmdPath

	if startNow:
		if saveScene:
			cmds.file(save=True)
		pid = os.spawnl(os.P_NOWAIT, batchCmdPath, batchCmdPath)
		print "start process of pid "+str(pid)


def	destroyHairstyle(hairstyle=None):

	# as assignment statements would make variables local implicitly, this global statement is necessary
	global __hairstyleBuilder, __hairstyleBuilderCallback

	if hairstyle:
		if not __hairstyleBuilder:
			__hairstyleBuilder = hairstyleBuilderClass(__moduleName)
			__hairstyleBuilderCallback = __hairstyleBuilder.callback
	
		__hairstyleBuilder.destroy(hairstyle)


def	cameraOptions():
	def f(x): return cmds.getAttr(x+".renderable")
	return	cmds.listRelatives(filter(f, cmds.ls(type='camera')), p=True)


def	batchRename(*args, **keywords):

	if 'prefix' not in keywords.keys():
		raise Exception, "argument error"

	if args:
		cmds.select(args)

	jc.helper.batchRename(prefix=keywords['prefix'])


def	convertFaceToOrderedVertices(face):

	edges = cmds.ls(cmds.polyListComponentConversion(face, te=True), l=True, fl=True)
	orderedVertices = cmds.ls(cmds.polyListComponentConversion(face, tv=True), l=True, fl=True)
	size = len(orderedVertices)

	if size == 0:
		raise Exception, "no face selected"

	orderedVertices = orderedVertices[:1]

	while len(orderedVertices) < size:
		for edge in edges:
			(a, b) = cmds.ls(cmds.polyListComponentConversion(edge, tv=True), l=True, fl=True)
			if a == orderedVertices[-1]:
				orderedVertices.append(b)
			elif b == orderedVertices[-1]:
				orderedVertices.append(a)
			else:
				continue
			edges.remove(edge)
			break

	return orderedVertices


def	createCurvesFromExtrude(numCurves=5):
# usage: select polygon objects or extrude nodes
# The objects have histories of extrusion and the extruded faces must be 4-sided.

	objects = cmds.ls(sl=True, l=True, fl=True)
	if not bool(objects):
		raise Exception, "no selection"

	for obj in objects:

		shape = cmds.ls(cmds.listRelatives(obj, s=True, f=True, ni=True), type="mesh", l=True, fl=True)
		extrudeNodes = []

		if bool(shape):
			obj = shape[0]
			extrudeNodes = cmds.ls(cmds.listHistory(obj), type="polyExtrudeFace")
		elif cmds.nodeType(obj) == "polyExtrudeFace":
			extrudeNodes = [obj]
			obj = cmds.listRelatives(cmds.ls(cmds.listHistory(obj, future=False), type="mesh", l=True), p=True, f=True)[0]
		else:
			continue

		group = cmds.createNode("transform", n="constructionN_1")
		output = cmds.createNode("transform", n="outputCurvesN_1")

		for x in extrudeNodes:

			try:
				cmds.setAttr(x+".kft", False, l=True)
				cmds.setAttr(x+".d", l=True)
			except:
				pass
			faces = cmds.getAttr(x+".inputComponents")

			if not bool(faces):
				continue

			def f(x): return obj+"."+x
			faces = cmds.ls(map(f, faces), l=True, fl=True)

			for face in faces:

				vertices = convertFaceToOrderedVertices(face)
				edges = cmds.ls(cmds.polyListComponentConversion(face, te=True), l=True, fl=True)

				# must be 4 edges
				if len(edges) != 4:
					continue

				curves = []
				for v in vertices:
					# select edge loop out from the vertice
					e = list(set(cmds.ls(cmds.polyListComponentConversion(v, te=True), l=True, fl=True)) - set(edges))[0]
					#cmds.polySelect(obj, el=int(e[:-1].split('[')[-1]))
					cmds.polySelect(obj, el=int("{1}".format(*re.split("\[|\]", e))))

					# reverse the selection so that the curve would start from the head
					a = cmds.ls(os=True)
					a.reverse()
					cmds.select(cl=True)
					[ cmds.select(b, add=True) for b in a ]

					# convert the edge loop to curve
					curves.append(cmds.polyToCurve(form=0, degree=3)[0])
					cmds.setAttr(curves[-1]+".v", False)

				# create surfaces from curves
				l1 = cmds.loft(curves[0], curves[1], ch=True, rn=False, po=0, n="edgeS_1")
				cmds.setAttr(l1[0]+".v", False)
				l2 = cmds.loft(curves[3], curves[2], ch=True, rn=False, po=0, n="edgeS_1")
				cmds.setAttr(l2[0]+".v", False)

				# create surfaces from lofted surfaces
				for i in range(numCurves):
					u = 1.0/numCurves * i
					surface = cmds.loft(l1[0]+".u["+str(u)+"]", l2[0]+".u["+str(u)+"]", ch=True, rn=False, po=0, n="edgeS_1")
					cmds.setAttr(surface[0]+".v", False)

					# create curves from surfaces
					for j in range(numCurves):
						u = 1.0/numCurves * j
						c = cmds.duplicateCurve(surface[0]+".u["+str(u)+"]", ch=True, rn=False, l=False, n="hairC_1")
						cmds.parent(c[0], output)

					cmds.parent(surface[0], group)
				cmds.parent(l1[0], group)
				cmds.parent(l2[0], group)
				cmds.parent(curves, group)


def	createHairUV():
# usage: select polygon objects

	objects = cmds.ls(sl=True, l=True, fl=True)
	if not bool(objects):
		raise Exception, "no selection"

	for obj in objects:
		shape = cmds.listRelatives(obj, s=True, f=True, ni=True)[0]
		if cmds.nodeType(shape) != "mesh":
			continue

		#faces = cmds.ls(cmds.polyListComponentConversion(shape, tf=True), fl=True, l=True)
		n = math.ceil(math.sqrt(cmds.polyEvaluate(shape, f=True)))

		projections = []
		maxWidth = 0
		#for face in faces:
		for i in range(cmds.polyEvaluate(shape, f=True)):
			face = shape+".f["+str(i)+"]"
			s = re.split("\s+", cmds.polyInfo(face, fn=True)[0])
			nx = float("{2}".format(*s))
			ny = float("{3}".format(*s))
			nz = float("{4}".format(*s))
			projections.append(cmds.polyProjection(face, ch=True, type='Planar', ibd=True, kir=True, md='b')[0])
			cmds.setAttr(projections[-1]+".rx", -math.degrees(math.asin(ny/math.sqrt(math.pow(nx,2)+math.pow(ny,2)+math.pow(nz,2)))) )
			cmds.setAttr(projections[-1]+".ry", math.degrees(math.atan(nx/nz)) )
			if ny < 0 or nz < 0:
				cmds.setAttr(projections[-1]+".ry", 180-math.degrees(math.atan(-nx/nz)) )
			cmds.setAttr(projections[-1]+".rz", 0 )
			if cmds.getAttr(projections[-1]+".pw") > maxWidth:
				maxWidth = cmds.getAttr(projections[-1]+".pw")
		i = j = 0.5/n
		for projection in projections:
			cmds.setAttr(projection+".pw", maxWidth)
			cmds.setAttr(projection+".ph", maxWidth)
			cmds.setAttr(projection+".isu", 1/n)
			cmds.setAttr(projection+".isv", 1/n)
			cmds.setAttr(projection+".icx", i)
			cmds.setAttr(projection+".icy", j)
			i += 1/n
			if i > 1:
				j += 1/n
				i = 0.5/n


def	createHairFollicles(density=40):
# usage: select polygon objects
# to ensure uniform follicle density, createHairUV() should be executed prior to this

	objects = cmds.ls(sl=True, l=True, fl=True)
	if not bool(objects):
		raise Exception, "no selection"

	for obj in objects:
		shape = cmds.listRelatives(obj, s=True, f=True, ni=True)[0]
		if cmds.nodeType(shape) != "mesh":
			continue

		for j in range(density):
			v = float(j)/float(density)
			for i in range(density):
				u = float(i)/float(density)
				t = cmds.createNode("transform")
				f = cmds.createNode("follicle", p=t)
				cmds.connectAttr(shape+".outMesh", f+".inputMesh", f=True)
				cmds.connectAttr(shape+".worldMatrix[0]", f+".inputWorldMatrix", f=True)
				cmds.connectAttr(f+".outTranslate", t+".translate", f=True)
				cmds.connectAttr(f+".outRotate", t+".rotate", f=True)
				cmds.setAttr(f+".pu", u)
				cmds.setAttr(f+".pv", v)
				if cmds.getAttr(f+".vuv"):
					#cmds.addAttr(f, at="short", sn="density", h=True)
					#cmds.setAttr(f+"."+"density", density)
					#cmds.addAttr(f, at="short", sn="faceIndex", h=True)
					#cmds.setAttr(f+"."+"faceIndex", )
					cmds.addAttr(f, at="short", sn="row", h=True)
					cmds.setAttr(f+"."+"row", j)
					cmds.addAttr(f, at="short", sn="column", h=True)
					cmds.setAttr(f+"."+"column", i)
				#else:
				#	cmds.delete(t)


def	createHairPatches():
# usage: select polygon objects
# createHairFollicles() should be executed prior to this

	objects = cmds.ls(sl=True, l=True, fl=True)
	if not bool(objects):
		raise Exception, "no selection"

	for obj in objects:
		shape = cmds.listRelatives(obj, s=True, f=True, ni=True)[0]
		if cmds.nodeType(shape) != "mesh":
			continue

		faces = cmds.ls(cmds.polyListComponentConversion(shape, tf=True), fl=True, l=True)
		
		for face in faces:
			vertices = convertFaceToOrderedVertices(face)

			corners = []
			points = []
			for v in vertices:
				corners.append(cmds.pointPosition(v))
			patch = cmds.polyCreateFacet(p=corners)[0]
			cmds.transferAttributes(shape, patch, pos=0, nml=0, uvs=2, col=2, spa=0, sus="map1", tus="map1", sm=3, fuv=0, clb=1)

			# find normal for curve projection
			s = re.split("\s+", cmds.polyInfo(patch+".f[0]", fn=True)[0])
			nx = float("{2}".format(*s))
			ny = float("{3}".format(*s))
			nz = float("{4}".format(*s))

			tempTransform = cmds.createNode("transform")
			tempFollicle = cmds.createNode("follicle", p=tempTransform)
			cmds.connectAttr(patch+".outMesh", tempFollicle+".inputMesh", f=True)
			cmds.connectAttr(patch+".worldMatrix[0]", tempFollicle+".inputWorldMatrix", f=True)
			cmds.connectAttr(tempFollicle+".outTranslate", tempTransform+".translate", f=True)
			cmds.connectAttr(tempFollicle+".outRotate", tempTransform+".rotate", f=True)
			for follicle in cmds.ls(cmds.listHistory(shape, f=True), type='follicle'):
				cmds.setAttr(tempFollicle+".pu", cmds.getAttr(follicle+".pu"))
				cmds.setAttr(tempFollicle+".pv", cmds.getAttr(follicle+".pv"))
				if cmds.getAttr(tempFollicle+".vuv") and cmds.getAttr(follicle+".vuv") and cmds.attributeQuery("row", n=follicle, ex=True) and cmds.attributeQuery("column", n=follicle, ex=True):
					points.append({ "row":cmds.getAttr(follicle+".row"), "column":cmds.getAttr(follicle+".column"), "translate":cmds.getAttr(tempTransform+".t")[0] })
			cmds.delete(tempTransform)

			# create curves
			directions = [ "row", "column" ]

			for direction in directions:
				curves = []
				nextDirection = list( set(directions) - set([direction]) )[0]

				directionIndexes = set([])
				for point in points:
					directionIndexes |= set([ point[direction] ])
				directionIndexes = list(directionIndexes)
				directionIndexes.sort()

				for i in directionIndexes:
					def f(x): return x[direction] == i
					pointsInDirection = filter(f, points)

					nextDirectionIndexes = set([])
					for point in pointsInDirection:
						nextDirectionIndexes |= set([ point[nextDirection] ])
					nextDirectionIndexes = list(nextDirectionIndexes)
					nextDirectionIndexes.sort()

					if len(nextDirectionIndexes) > 1:

						for point in pointsInDirection:
							if point[nextDirection] == nextDirectionIndexes[0]:
								start = point["translate"]
							elif point[nextDirection] == nextDirectionIndexes[-1]:
								end = point["translate"]

						curves.append(cmds.curve(d=1, p=[start, end], k=[0, 1]))

				# project curves (of the same direction) onto patch
				# (polySplit node is not able to handle curves which are crossing each other)
				if len(curves) > 0:
					splitNode = cmds.createNode("polySplit")
					patchShape = cmds.listRelatives(patch, s=True, ni=True, f=True)[0]
					cmds.connectAttr(patchShape+".outMesh", splitNode+".inputPolymesh", f=True)

					for curve in curves:
						cmds.xform(curve, cp=True)
						cmds.scale(3,3,3, curve)		# TBD: determine if it's enough to cut the borders
						(grp, projectNode) = cmds.polyProjectCurve(patch, curve, ch=True, direction=(nx,ny,nz))
						cmds.setAttr(projectNode+".pointsOnEdges", True)
						cmds.setAttr(projectNode+".automatic", True)
						size = cmds.getAttr(splitNode+".splitPoints", s=True)
						cmds.connectAttr(projectNode+".curvePoints[0]", splitNode+".splitPoints["+str(size)+"]")

					cmds.setAttr(patchShape+".intermediateObject", True)
					mesh = cmds.createNode("mesh", p=patch)
					cmds.connectAttr(splitNode+".output", mesh+".inMesh", f=True)


def	extrudeHairPatches():
# find extrude node in hair model
# extrude hair patch and copy attributes
# delete history
# wrap hair patch with hair model
# find follicles on patch
# create curves from loop edges at follicle positions
# connect dynamics...
	pass


def	createHairBrush():
# select curves

	curves = cmds.ls(sl=True)
	if not bool(curves):
		raise Exception, "no selection"
	curves = cmds.listRelatives(curves, s=True)
	if not bool(curves):
		raise Exception, "no shape selected"
	curves = cmds.ls(curves, type="nurbsCurve", l=True)
	if not bool(curves):
		raise Exception, "no NURBS curve selected"

	for curve in curves:
		t = cmds.createNode("transform")
		s = cmds.createNode("stroke", p=t)
		b = cmds.createNode("brush")
		cmds.connectAttr(b+".outBrush", s+".brush")
		cmds.connectAttr(curve+".worldSpace[0]", s+".controlCurve[0]")
		cmds.connectAttr(curve+".worldSpace[0]", s+".pathCurve[0].curve")
		# apply hair preset to stroke and brush


def	createHairModifier():
# select curves
# modifier =  smoothCurve -> detachCurve -> rebuildCurve

	curves = cmds.ls(sl=True)
	if not bool(curves):
		raise Exception, "no selection"
	curves = cmds.listRelatives(curves, s=True)
	if not bool(curves):
		raise Exception, "no shape selected"
	curves = cmds.ls(curves, type="nurbsCurve", l=True)
	if not bool(curves):
		raise Exception, "no NURBS curve selected"

	for curve in curves:
		transform = cmds.listRelatives(curve, p=True, ni=True)[0]
		curveShape = cmds.createNode("nurbsCurve", p=transform)
		smooth = cmds.createNode("smoothCurve")
		detach = cmds.createNode("detachCurve")
		rebuild = cmds.createNode("rebuildCurve")
		cmds.setAttr(curve+".intermediateObject", False)
		cmds.connectAttr(curve+".worldSpace[0]", smooth+".ic")
		cmds.connectAttr(smooth+".oc", detach+".ic")
		cmds.connectAttr(detach+".oc[0]", rebuild+".ic")
		cmds.connectAttr(rebuild+".oc", curveShape+".create")
		cmds.setAttr(curve+".intermediateObject", True)
		cmds.setAttr(smooth+".s", 0)
		for i in range(int(cmds.getAttr(curve+".max")+2)):
			cmds.setAttr(smooth+".i["+str(i)+"]", i)		# use expression or script node to update this
		cmds.setAttr(detach+".p[0]", cmds.getAttr(curve+".max"))
		cmds.setAttr(detach+".k[0]", True)
		cmds.setAttr(rebuild+".s", cmds.getAttr(curve+".max"))
		cmds.setAttr(rebuild+".kcp", True)

		(x,y,z) = cmds.pointOnCurve(curveShape, pr=0, p=True)
		cmds.xform(transform, piv=[x,y,z])


def	doMenu(do=True, parent=None):
	jc.menu.destroyMenu(__moduleName)

	if do:
		if parent:
			if isinstance(parent, jc.menu.subMenuItem):
				m = parent
			elif not (isinstance(parent, types.StringType) or isinstance(parent, types.UnicodeType)) \
				or cmds.objectTypeUI(parent) != "floatingWindow":
				parent = None
		if not parent:
			m = jc.menu.createMenu(__moduleName, parent)

		i = jc.menu.commandItem(m, __moduleName+".hairstyleBuilder", "Hairstyle Builder", annotation="Open Hairstyle Builder")
		jc.menu.listOption(i, "hairstyle", hairstyleOptions()[0], hairstyleOptions)

		jc.menu.dividerItem(m)

		i = jc.menu.commandItem(m, __moduleName+".createHairSystems", "Create Hair Systems", annotation="Select NURBS patch(es)")
		jc.menu.listOption(i, "hair Direction", directionOptions()[0], directionOptions, True)
		jc.menu.listOption(i, "extract", extractOptions()[0], extractOptions, True)
		jc.menu.integerOption(i, "curve Count", 5)
		jc.menu.booleanOption(i, "visible Only", True, True)
		jc.menu.listOption(i, "hair System Preset", getHairSystemPresetsCallback()[0], getHairSystemPresetsCallback)

		i = jc.menu.commandItem(m, __moduleName+".convertPFX2Shave", "Convert PFX to Shave", annotation="Select pfxHair nodes")
		jc.menu.listOption(i, "shave Preset", getShaveHairPresetsCallback()[0], getShaveHairPresetsCallback)
		jc.menu.booleanOption(i, "match Hair Count", True)
		jc.menu.listOption(i, "shave Nodes", shaveNodesOptions()[0], shaveNodesOptions)
		jc.menu.booleanOption(i, "delete History", False, True)

		i = jc.menu.commandItem(m, __moduleName+".createHairs", "Create Hairs", annotation="Select NURBS patch(es)")
		jc.menu.listOption(i, "hair Direction", directionOptions()[1], directionOptions, True)
		jc.menu.listOption(i, "extract", extractOptions()[0], extractOptions, True)
		jc.menu.integerOption(i, "curve Count", 5)
		jc.menu.booleanOption(i, "visible Only", True, True)
		jc.menu.booleanOption(i, "match Hair Count", True)
		jc.menu.listOption(i, "shave Nodes", shaveNodesOptions()[0], shaveNodesOptions)
		jc.menu.listOption(i, "hair System Preset", getHairSystemPresetsCallback()[0], getHairSystemPresetsCallback)
		jc.menu.listOption(i, "shave Preset", getShaveHairPresetsCallback()[0], getShaveHairPresetsCallback)
		jc.menu.listOption(i, "shave Globals Preset", getShaveGlobalsPresetsCallback()[0], getShaveGlobalsPresetsCallback, True)
		jc.menu.booleanOption(i, "polygon", True)
		jc.menu.listOption(i, "render Layer", getRenderLayersCallback()[0], getRenderLayersCallback, True)
		jc.menu.listOption(i, "render Layer Shadow", getRenderLayersCallback()[0], getRenderLayersCallback, True)
		jc.menu.booleanOption(i, "delete History", False, True)

		i = jc.menu.commandItem(m, __moduleName+".createPolygonHair", "Create Polygon Hair", annotation="Select pfxHair nodes")
		#jc.menu.stringOption(i, "file Name", "")
		#jc.menu.listOption(i, "file Type", fileTypeOptions()[0], fileTypeOptions)
		jc.menu.listOption(i, "render Layer Shadow", getRenderLayersCallback()[0], getRenderLayersCallback, True)
		jc.menu.integerOption(i, "poly Limit", 500000)
		jc.menu.booleanOption(i, "delete History", False, True)

		i = jc.menu.commandItem(m, __moduleName+".createNClothWrapDeformer", "Create nCloth Wrap Deformer", annotation="Select NURBS patches and a passive collision object")
		jc.menu.listOption(i, "hair Direction", directionOptions()[1], directionOptions, True)
		jc.menu.listOption(i, "nCloth Preset", getNClothPresetsCallback()[0], getNClothPresetsCallback)

		i = jc.menu.commandItem(m, __moduleName+".batchRender", "Batch Render", annotation="Render scene in batch mode")
		jc.menu.listOption(i, "camera", cameraOptions()[0], cameraOptions)
		jc.menu.listOption(i, "render Layer", getRenderLayersCallback()[0], getRenderLayersCallback, True)
		jc.menu.booleanOption(i, "start Now", True)
		jc.menu.booleanOption(i, "save Scene", True)
		jc.menu.booleanOption(i, "shutdown", False)
		jc.menu.integerOption(i, "start Frame", 1)
		jc.menu.integerOption(i, "end Frame", 24)

		i = jc.menu.commandItem(m, __moduleName+".destroyHairstyle", "Destroy Hairstyle", annotation="Delete nodes under a hairstyle definition")
		jc.menu.listOption(i, "hairstyle", "None", hairstyleOptions1)

		jc.menu.dividerItem(m)

		i = jc.menu.commandItem(m, __moduleName+".connectShaveNodes", "Connect Shave Nodes", annotation="Select NURBS patch(es)")
		jc.menu.checkboxOption(i, "attributes", getShaveHairAttributes(), getShaveHairAttributes)

		i = jc.menu.commandItem(m, __moduleName+".disconnectShaveNodes", "Disconnect Shave Nodes", annotation="Select NURBS patch(es)")

		i = jc.menu.commandItem(m, __moduleName+".deleteShaveNodes", "Delete Shave Nodes", annotation="Select NURBS patch(es)")
		jc.menu.booleanOption(i, "delete Input Curves", True)

		i = jc.menu.commandItem(m, __moduleName+".updateHairOcclusionObjects", "Update Hair Occlusion Objects", annotation="Select object(s)")

		i = jc.menu.commandItem(m, __moduleName+".hideHairInRenderLayers", "Hide Hair in Render Layers", annotation="Select NURBS patch(es)")
		jc.menu.listOption(i, "exception", getRenderLayersCallback()[0], getRenderLayersCallback, True)

		jc.menu.dividerItem(m)

		i = jc.menu.commandItem(m, __moduleName+".createHairClumps", "Create Hair Clumps", annotation="Select NURBS patch(es)")
		jc.menu.listOption(i, "hair Direction", directionOptions()[1], directionOptions, True)
		jc.menu.listOption(i, "extract", extractOptions()[0], extractOptions, True)
		jc.menu.integerOption(i, "curve Count", 5)
		jc.menu.booleanOption(i, "visible Only", True, True)

		i = jc.menu.commandItem(m, __moduleName+".trim", "Trim", annotation="Select NURBS curve(s) anc/or surface(s)")
		jc.menu.listOption(i, "hair Direction", directionOptions()[1], directionOptions, True)
		jc.menu.floatOption(i, "ratio", 0.5)
		jc.menu.booleanOption(i, "randomize", True)
		jc.menu.listOption(i, "trim", trimOptions()[0], trimOptions)

		i = jc.menu.commandItem(m, __moduleName+".displace", "Displace", annotation="Select NURBS curve(s) anc/or surface(s)")
		jc.menu.floatOption(i, "amplitude", 3.0)
		jc.menu.listOption(i, "displace", displaceOptions()[0], displaceOptions)

		i = jc.menu.commandItem(m, __moduleName+".convertClumps2Shave", "Convert Clumps to Shave", annotation="Select hair clumps (groups of curves)")
		jc.menu.listOption(i, "shave Preset", getShaveHairPresetsCallback()[0], getShaveHairPresetsCallback)
		jc.menu.booleanOption(i, "match Hair Count", True, True)
		jc.menu.listOption(i, "shave Nodes", shaveNodesOptions()[0], shaveNodesOptions, True)

		i = jc.menu.commandItem(m, __moduleName+".createJointChain", "Create Joint Chain", annotation="Select NURBS patch(es)")
		jc.menu.listOption(i, "hair Direction", directionOptions()[1], directionOptions, True)

		i = jc.menu.commandItem(m, __moduleName+".createHelixPatch", "Create Helix Patch")
		jc.menu.listOption(i, "hair Direction", directionOptions()[1], directionOptions, True)
		jc.menu.floatOption(i, "radius", 1.0)
		jc.menu.floatOption(i, "height", 5.0)
		jc.menu.floatOption(i, "width", 0.5)
		jc.menu.integerOption(i, "coils", 4)
		jc.menu.booleanOption(i, "construction History", True)

		jc.menu.dividerItem(m)

		i = jc.menu.commandItem(m, __moduleName+".touchShaveHair", "Touch Shave Hair", annotation="Revert Shave hair appearance")

		i = jc.menu.commandItem(m, __moduleName+".batchRename", "Batch Rename", annotation="Select object(s)")
		jc.menu.stringOption(i, "prefix", "")
