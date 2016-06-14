import types, os
import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMaya as OpenMaya


def	findTypeInHistory(obj, type, future=False, past=True):
# This is translated from the mel procedure of the same name.

	if past and future:
		# In the case that the object type exists in both past and future
		# find the one that is fewer connections away.
		pasts = cmds.listHistory(obj, f=0, bf=1, af=1)
		futures = cmds.listHistory(obj, f=1, bf=1, af=1)
		pastObjs = cmds.ls(pasts, type=type)
		futureObjs = cmds.ls(futures, type=type)
		if len(pastObjs) > 0:
			if len(futureObjs) > 0:
				for i in range( min( len(pasts), len(futures) ) ):
					if pasts[i] == pastObjs[0]:
						return pastObjs[0]
					if futures[i] == futureObjs[0]:
						return futureObjs[0]
			else:
				return pastObjs[0]
		elif len(futureObjs) > 0:
			return futureObjs[0]
	else:
		if past:
			hist = cmds.listHistory(obj, f=0, bf=1, af=1)
			objs = cmds.ls(hist, type=type)
			if len(objs) > 0:
				return objs[0]
		if future:
			hist = cmds.listHistory(obj, f=1, bf=1, af=1)
			objs = cmds.ls(hist, type=type)
			if len(objs) > 0:
				return objs[0]

	return None


def	getVertexUV():
# usage: select uv components
# return: a dictionary in which key is uv component index, value is a tuple of (u,v)

	slist = OpenMaya.MSelectionList()
	OpenMaya.MGlobal.getActiveSelectionList( slist )
	if slist.length() == 0:
		raise Exception, "nothing selected"

	component = OpenMaya.MObject()
	mesh = OpenMaya.MDagPath()
	slist.getDagPath(0, mesh, component)

	if component.isNull():
		raise Exception, "no component is selected"

	dagNodeFn = OpenMaya.MFnDagNode()
	dagNodeFn.setObject(mesh)

	if dagNodeFn.typeName() != "mesh":
		raise Exception, "selection is not a mesh"

	if component.apiType() != OpenMaya.MFn.kMeshMapComponent:
		raise Exception, "selection is not a UV component"

	selUVs = OpenMaya.MIntArray()
	compFn = OpenMaya.MFnSingleIndexedComponent(component)
	compFn.getElements(selUVs)
	if selUVs.length() < 1:
		raise Exception, "invalid selection"

	uScriptUtil = OpenMaya.MScriptUtil()
	vScriptUtil = OpenMaya.MScriptUtil()
	uPtr = uScriptUtil.asFloatPtr()
	vPtr = vScriptUtil.asFloatPtr()

	meshFn = OpenMaya.MFnMesh()
	meshFn.setObject(mesh)
	
	uv = {}
	for i in selUVs:
		meshFn.getUV(i, uPtr, vPtr)
		uv[i] = ( float(uScriptUtil.getFloat(uPtr)), float(vScriptUtil.getFloat(vPtr)) )

	return uv
	

def	getKnots(direction="U"):
# usage: one nurbs object
# return: a list containing positions of isoparms along given direction

	if type(direction) != types.StringType:
		raise Exception, "invalid argument"
	if direction.upper() != "U" and direction.upper() != "V":
		raise Exception, "invalid argument: "+direction

	slist = OpenMaya.MSelectionList()
	OpenMaya.MGlobal.getActiveSelectionList( slist )
	if slist.length() == 0:
		raise Exception, "Nothing selected"
	elif slist.length() > 1:
		raise Exception, "Too many objects selected"

	component = OpenMaya.MObject()
	surface = OpenMaya.MDagPath()
	slist.getDagPath(0, surface, component)

	dagNodeFn = OpenMaya.MFnDagNode()
	dagNodeFn.setObject(surface)

	if dagNodeFn.typeName() != "nurbsSurface":
		try:
			surface.extendToShape()
		except:
			raise Exception, "Could not find surface"

	dagNodeFn.setObject(surface)

	if dagNodeFn.typeName() != "nurbsSurface":
		raise Exception, "selection is not a nurbsSurface"

	surfaceFn = OpenMaya.MFnNurbsSurface()
	surfaceFn.setObject(surface)
	a = OpenMaya.MDoubleArray()
	if direction.upper() == "U":
		surfaceFn.getKnotsInU(a)
	else:
		surfaceFn.getKnotsInV(a)
		
	return a[2:-2]


def	batchRename(prefix):
	if not prefix:
		raise Exception, "empty prefix"
	def m(obj):
		maptype = { 'transform': 'N',
			'nurbsCurve': 'C',
			'nurbsSurface': 'S',
			'mesh': 'S',
			'locator': 'Loc',
			'camera': 'Cam',
			'ambientLight': 'Light',
			'directionalLight': 'Light',
			'pointLight': 'Light',
			'areaLight': 'Light',
			'spotLight': 'Light',
			'volumeLight': 'Light',
			'renderLayer': 'RL',
			'displayLayer': 'L',
			'joint': 'J'
			}
		if not cmds.listRelatives(obj, s=True, f=True) and cmds.nodeType(obj) == 'transform':
			type = 'N'
		else:
			t = cmds.listRelatives(obj, s=True, f=True)
			if t:
				t = cmds.nodeType(t[0])
			else:
				t = cmds.nodeType(obj)
			if t in maptype.keys():
				type = maptype[t]
			else:
				type = t
		return obj, type
	return [ cmds.rename(x, prefix+y+'_#') for x,y in map(m, cmds.ls(sl=True, l=True)) ]


def	getPresets(node, includeUser=True):
	presetPaths = []
	if 'MAYA_LOCATION' in os.environ:
		presetPaths.append(os.path.join(os.path.join(os.environ['MAYA_LOCATION'], "presets"), "attrPresets"))

	if 'MAYA_PRESET_PATH' in os.environ:
		for p in os.environ['MAYA_PRESET_PATH'].split([':',';'][cmds.about(nt=True)]):
			presetPaths.append(os.path.join(p, "attrPresets"))

	if includeUser:
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


def	applyAttrPreset(node, preset):
	if preset in getPresets(cmds.nodeType(node), False):
		if 'MAYA_PRESET_PATH' in os.environ and preset[-4:] != '.mel':
			for p in os.environ['MAYA_PRESET_PATH'].split([':',';'][cmds.about(nt=True)]):
				p = os.path.join(os.path.join(os.path.join(p, "attrPresets"), cmds.nodeType(node)), preset+'.mel')
				if os.path.exists(p):
					preset = p
					break
		if 'MAYA_LOCATION' in os.environ and preset[-4:] != '.mel':
			p = os.path.join(os.path.join(os.path.join(os.path.join(os.environ['MAYA_LOCATION'], "presets"), "attrPresets"), cmds.nodeType(node)), preset+'.mel')
			if os.path.exists(p):
				preset = p

	count = 2
	while count:
		try:
			preset = preset.replace('\\', '/')
			mel.eval("applyAttrPreset(\""+node+"\", \""+preset+"\", 1)")
			count = 0
		except:
			mel.eval("AttributeEditor;openAEWindow;commitAENotes($gAECurrentTab);window -e -vis 0 AEWindow;")


def	getUVAtPoint(objList, mesh):
# usage: for objects in objList, UVs of the points closest to the objects on the mesh will be found
# return: list of tuples of (u,v)

	olist = OpenMaya.MSelectionList()
	for o in objList:
		olist.add(o)
	mlist = OpenMaya.MSelectionList()
	mlist.add(mesh)

	mesh = OpenMaya.MDagPath()
	mlist.getDagPath(0, mesh)
	meshFn = OpenMaya.MFnMesh()
	meshFn.setObject(mesh)

	uvPairs = []
	scriptUtil = OpenMaya.MScriptUtil()
	uvPtr = scriptUtil.asFloat2Ptr()
	transformFn = OpenMaya.MFnTransform()
	point = OpenMaya.MDagPath()

	for i in range(olist.length()):
		olist.getDagPath(i, point)
		transformFn.setObject(point)
		pt = transformFn.getTranslation(OpenMaya.MSpace.kWorld)
	
		meshFn.getUVAtPoint(OpenMaya.MPoint(pt), uvPtr, OpenMaya.MSpace.kWorld)

		uvPairs.append(
			( float(scriptUtil.getFloat2ArrayItem(uvPtr, 0, 0)), float(scriptUtil.getFloat2ArrayItem(uvPtr, 0, 1)) )
		)

	return uvPairs


def	createFollicle(obj, uv):

	fol = cmds.createNode("follicle")
	folTform = cmds.listRelatives(fol, p=True)[0]
	cmds.connectAttr(obj + ".outMesh", fol + ".inputMesh")
	cmds.connectAttr(obj + ".worldMatrix[0]", fol + ".inputWorldMatrix")
	cmds.connectAttr(fol + ".outTranslate", folTform + ".translate" )
	cmds.connectAttr(fol + ".outRotate", folTform + ".rotate")
	cmds.setAttr(fol+".parameterU", uv[0])
	cmds.setAttr(fol+".parameterV", uv[1])

	return folTform
