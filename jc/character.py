# character.py
# This is a collection of character (rigging, modeling, texturing) related scripts.
#
# Installation:
# This file implements the module called jc.character.
# Under Maya script directory, create a directory called 'jc', put an empty file '__init__.py' and this file under there.
# Add PYTHONPATH to point to script directory in Maya.env.
#
# Author's website:
# http://sites.google.com/site/cgriders


import types, math, re
import maya.cmds as cmds
import maya.OpenMaya as OpenMaya
import maya.mel as mel
import jc.menu, jc.clothes

__moduleName = "jc.character"
__skinTypeAttr = "skinType"
__skinTypeAttrValues = { "skinCluster":0, "nCloth":1, "poseDeformer":2, "blendShape":3 }

###############################################################################

# Workflow tools to translate nCloth skin to PSD or blendShape deformed skin


def	__duplicateSkin(*args, **keywords):
# usage: select only one skin (mesh having skinCluster in history)

	s = args
	if not args:
		s = cmds.ls(sl=True)
	if not s:
		raise Exception, "no selection"
	elif len(s) > 1:
		raise Exception, "more than one object is selected"

	skinCluster = cmds.ls(cmds.listHistory(s), type='skinCluster')	
	if not skinCluster:
		raise Exception, "object has not been bound"

	skin = cmds.createNode('mesh', p=cmds.listRelatives(s, p=True, f=True)[0])
	cmds.connectAttr(skinCluster[0]+'.outputGeometry[0]', skin+'.inMesh')
	cmds.sets(skin, fe='initialShadingGroup', e=True)
	return skin


def	__findSkin(j, deformer):
# return either skinCluster skin, ncloth skin, poseDeformer or blendShape skin
	skins = cmds.ls(cmds.listHistory(j, f=True), type='mesh')
	dskin = deformerNode = None
	for skin in skins:
		if deformer == "skinCluster":
			d = cmds.ls(cmds.listHistory(skin, lv=1), type=deformer)
		else:
			d = cmds.ls(cmds.listHistory(skin), type=deformer)
			if deformer == "blendShape":
				if cmds.ls(cmds.listHistory(skin), type="nCloth") or cmds.ls(cmds.listHistory(skin), type="poseDeformer") or len(cmds.ls(cmds.listHistory(skin, f=True), type="mesh")) > 1:
					continue
		if d:
			deformerNode = d[0]
			dskin = skin
	if deformerNode and (cmds.ls(cmds.listHistory(deformerNode), type='skinCluster') or cmds.ls(cmds.listHistory(deformerNode, f=True), type='skinCluster')):
		return dskin


def	__extractDelta():
	pass


def	createDeformer(*args, **keywords):
#	Create poseDeformer/blendShape for a specific joint, one joint can only have one deformer connected to it
# It can be executed two times to create both poseDeformer and blendShape deformed skin on the same skin
#	PSD plugin is required
#	The skin must be an nCloth skin
# usage: select joint, it will find out the skin and apply poseDeformer/blendShape to it

	if 'deformer' not in keywords:
		raise Exception, "missing argument Deformer"
	deformer = keywords['deformer']

	if deformer == "poseDeformer":
		for p in [ "poseReader", "poseDeformer" ]:
			if not cmds.pluginInfo(p, q=True, loaded=True):
				if p in cmds.pluginInfo(ls=True):
					cmds.loadPlugin(p)
				else:
					raise Exception, p+" plugin not found"

	slist = args
	if not args:
		slist = cmds.ls(sl=True, type='joint')
	if not slist:
		raise Exception, "no joint selected"

	for j in slist:
		p = cmds.ls(cmds.listConnections(j, d=True), type=deformer)

		if p:
			print j+" has already been associated with "+p[0]
		else:
			sskin = __findSkin(j, "skinCluster")
			nskin = __findSkin(j, "nCloth")
			pskin = __findSkin(j, deformer)
			if not pskin:
				pskin = __duplicateSkin(nskin)
			elif deformer == "blendShape":
				print j+" has already been associated with "+cmds.ls(cmds.listHistory(pskin), type="blendShape")[0]
				continue

			t = cmds.listRelatives(pskin, p=True, f=True)[0]

			# throw away skinType attribute before creating deformer

			if cmds.attributeQuery(__skinTypeAttr, n=t, ex=True):
				skins = cmds.ls(cmds.listHistory(cmds.listConnections(t+'.'+__skinTypeAttr, d=True), f=True, lv=0, il=0), type='mesh')
				# delete the animCurveUU nodes for driven key
				cmds.delete(cmds.listConnections(t+'.'+__skinTypeAttr, d=True))
				cmds.deleteAttr(t, at=__skinTypeAttr)
				for s in skins:
					cmds.setAttr(s+'.intermediateObject', 1)
			else:
				cmds.setAttr(nskin+'.intermediateObject', 1)
			cmds.setAttr(pskin+'.intermediateObject', 0)

			# create deformer

			if deformer == "blendShape":
				deformerNode = cmds.blendShape(t, foc=True)[0]
				bskin = __findSkin(j, "poseDeformer")
			else:
				deformerNode = cmds.deformer(t, type=deformer)[0]
				cmds.connectAttr(j+".worldMatrix", deformerNode+".worldMatrix[0]", f=True)
				cmds.setAttr(deformerNode+".avgPoseSepRBF", 30.0)
				bskin = __findSkin(j, "blendShape")

			# create and connect/re-connect skinType attribute after creating deformer

			enumString = ""
			if bskin:
				keys = __skinTypeAttrValues.keys()
			else:
				keys = [ "nCloth", deformer ]
			for k in keys:
				enumString += k+"="+str(__skinTypeAttrValues[k])+":"

			cmds.addAttr(t, ln=__skinTypeAttr, at="enum", en=enumString)
			cmds.setAttr(t+'.'+__skinTypeAttr, keyable=True)

			blendShapeNode = None
			if deformer == "blendShape":
				blendShapeNode = deformerNode
			else:
				blendShapeNode = cmds.ls(cmds.listHistory(nskin), type='blendShape')
				if blendShapeNode:
					blendShapeNode = blendShapeNode[0]

			for k in keys:
				cmds.setAttr(t+'.'+__skinTypeAttr, __skinTypeAttrValues[k])
				if k == "skinCluster":
					cmds.setAttr(sskin+'.intermediateObject', 0)
					cmds.setAttr(nskin+'.intermediateObject', 1)
					cmds.setAttr(pskin+'.intermediateObject', 1)
				elif k == "nCloth":
					cmds.setAttr(sskin+'.intermediateObject', 1)
					cmds.setAttr(nskin+'.intermediateObject', 0)
					cmds.setAttr(pskin+'.intermediateObject', 1)
					if bskin:
						cmds.setAttr(bskin+'.intermediateObject', 1)
				elif k == deformer:
					cmds.setAttr(sskin+'.intermediateObject', 1)
					cmds.setAttr(nskin+'.intermediateObject', 1)
					cmds.setAttr(pskin+'.intermediateObject', 0)
					if bskin:
						cmds.setAttr(bskin+'.intermediateObject', 1)
				else:
					cmds.setAttr(sskin+'.intermediateObject', 1)
					cmds.setAttr(nskin+'.intermediateObject', 1)
					cmds.setAttr(pskin+'.intermediateObject', 1)
					if bskin:
						cmds.setAttr(bskin+'.intermediateObject', 0)

				if blendShapeNode:
					if k == "blendShape":
						cmds.setAttr(blendShapeNode+'.nodeState', 0)
						cmds.setDrivenKeyframe(blendShapeNode+'.nodeState', currentDriver=t+'.'+__skinTypeAttr)
					else:
						cmds.setAttr(blendShapeNode+'.nodeState', 1)
						cmds.setDrivenKeyframe(blendShapeNode+'.nodeState', currentDriver=t+'.'+__skinTypeAttr)

				cmds.setDrivenKeyframe(sskin+'.intermediateObject', currentDriver=t+'.'+__skinTypeAttr)
				cmds.setDrivenKeyframe(nskin+'.intermediateObject', currentDriver=t+'.'+__skinTypeAttr)
				cmds.setDrivenKeyframe(pskin+'.intermediateObject', currentDriver=t+'.'+__skinTypeAttr)
				if bskin:
					cmds.setDrivenKeyframe(bskin+'.intermediateObject', currentDriver=t+'.'+__skinTypeAttr)

			cmds.setAttr(t+'.'+__skinTypeAttr, __skinTypeAttrValues[deformer])

	cmds.select(slist, r=True)


def	copyPose(*args, **keywords):
#	A deformer must have been created with the above createDeformer() command
# The destination skin, PSD or blendShape, is determined by the Skin Type attribute
# If Skin Type is nCloth, no action will be performed
# If both PSD and blendShape Skin Types are present, the copy must be done two times
#	usage: select joint

	slist = args
	if not args:
		slist = cmds.ls(sl=True, type='joint')
	if not slist:
		raise Exception, "no joint selection"

	for j in slist:
		p = cmds.ls(cmds.listConnections(j, d=True), type='poseDeformer')
		if p:
			mesh = cmds.listConnections(p[0]+'.outputGeometry[0]', d=True, sh=True)
			nc = cmds.ls(cmds.listHistory(j, f=True), type='nCloth')
			cloth = cmds.listConnections(nc[0]+'.outputMesh', d=True, sh=True)

			# the following scripts are translated from poseDeformer_createPose() in poseDeformerUI.mel

			# find next available pose index
			i = cmds.getAttr(p[0]+'.pose', s=True)

			# determine pose name using joint name and pose index
			r = re.compile('(?P<first>[^\|]*)([\|](?P<last>[^\|]+))*$')
			m = r.match(j)
			prefix = m.group('first')
			if m.group('last'):
				prefix = m.group('last')
			pose = prefix + '_' + str(i)

			mel.eval("poseDeformerEdit -geo "+cloth[0]+" -xform "+j+" -pi "+str(i)+" "+p[0])

			poseNode = cmds.createNode('poseReader', n=pose)
			cmds.connectAttr(j+'.worldMatrix', poseNode+'.worldMatrixLiveIn', f=True)
			t = cmds.listRelatives(poseNode, p=True, f=True)[0]
			cmds.connectAttr(t+".worldMatrix", poseNode+".worldMatrixPoseIn", f=True)
			cmds.addAttr(poseNode, ln="weight", k=True)
			cmds.connectAttr(poseNode+".outWeight", poseNode+".weight")
			t = cmds.ls(cmds.parent(t, cmds.listRelatives(j, p=True, f=True)[0]), l=True)

			p1 = cmds.pointConstraint(j, t, w=1)
			o1 = cmds.orientConstraint(j, t, w=1)
			cmds.delete(p1, o1)

			animCurve = cmds.createNode("animCurveUU")
			cmds.setKeyframe(animCurve, f=0.0, v=1.0, itt="flat", ott="flat")
			cmds.setKeyframe(animCurve, f=0.25, v=0.85, itt="spline", ott="spline")
			cmds.setKeyframe(animCurve, f=0.75, v=0.15, itt="spline", ott="spline")
			cmds.setKeyframe(animCurve, f=1.0, v=0.0, itt="flat", ott="flat")
			cmds.connectAttr(animCurve+".message", poseNode+".msgAnimCurve", f=True)
			cmds.connectAttr(animCurve+".output", poseNode+".animCurveOutput", f=True)
			cmds.setAttr(poseNode+".readAxis", cmds.getAttr(j+".rotateOrder") % 3)
			cmds.setAttr(poseNode+".maxAngle", 45.0)

			cmds.setAttr(p[0]+".pose["+str(i)+"].poseName", pose, type="string")
			cmds.connectAttr(t[0]+".worldMatrix", p[0]+".pose["+str(i)+"].poseXForm[0].poseXFormWorldMatrix", f=True)
			cmds.connectAttr(poseNode+".readAxis", p[0]+".pose["+str(i)+"].poseXForm[0].poseXFormReadAxis", f=True)
			cmds.connectAttr(poseNode+".weight", p[0]+".pose["+str(i)+"].poseWeight")
			cmds.setAttr(p[0]+".pose["+str(i)+"].poseActive", 1)
			cmds.setAttr(p[0]+".envelope", 1.0)
		else:
			print p+" is not associated with any pose deformer. Ignored."

	cmds.select(slist, r=True)


def	deformerOptions():
	return [ "poseDeformer", "blendShape" ]


###############################################################################

# Facial rigging tools


def	groupJoint(*args, **keywords):
# Create a parent group for each selected joints. The purpose is to freeze joint attributes to zero.
# TBD: it fails when joints in a hierarchy are selected, their paths are changed during the for loop
#      fix: process children first

	joints = cmds.ls(sl=True, type="joint", l=True)

	if joints == None:
		raise Exception, "No joint selected"

	for joint in joints:
		g = cmds.group(em=True)
		cmds.parent(g, joint, r=True)
		p = cmds.listRelatives(joint, p=True, f=True)
		cmds.parent(g, p, r=False)
		joint = cmds.parent(joint, g, r=False)[0]
		cmds.setAttr(joint+".jointOrient", 0, 0, 0)
		cmds.setAttr(joint+".rotate", 0, 0, 0)


def	createFacialControlRig(*args, **keywords):
# usage: select root joint of the bound rig which will be duplicated and connected to the control rig with constraints
	pass

def	createFacialPoseNode(*args, **keywords):
# usage: select a node
	pass

def	saveFacialPose(*args, **keywords):
# usage: select facial pose node
# create attribute on pose node, pose node has connections to joints, follow the connections, create group node on top of the joint and set driven keys
	pass

# select -r upperLipJ_smile_1 ;
# setAttr "upperLipJ_smile_1.rotateZ" 0;
# setAttr "upperLipJ_smile_1.translateX" 0;
# setAttr "upperLipJ_smile_1.translateY" 0;
# setAttr "upperLipJ_smile_1.translateZ" 0;
# setAttr "upperLipJ_smile_1.rotateX" 0;
# setAttr "upperLipJ_smile_1.rotateY" 0;
# setDrivenKeyframe -currentDriver poses.smile upperLipJ_smile_1.translateX;
# setDrivenKeyframe -currentDriver poses.smile upperLipJ_smile_1.translateY;
# setDrivenKeyframe -currentDriver poses.smile upperLipJ_smile_1.translateZ;
# setDrivenKeyframe -currentDriver poses.smile upperLipJ_smile_1.rotateX;
# setDrivenKeyframe -currentDriver poses.smile upperLipJ_smile_1.rotateY;
# setDrivenKeyframe -currentDriver poses.smile upperLipJ_smile_1.rotateZ;
# setDrivenKeyframe -currentDriver poses.smile upperLipJ_smile_1.scaleX;
# setDrivenKeyframe -currentDriver poses.smile upperLipJ_smile_1.scaleY;
# setDrivenKeyframe -currentDriver poses.smile upperLipJ_smile_1.scaleZ;
	
def	mirrorFacialPose(*args, **keywords):
# usage: select joints on the left
# left and right joints are connected, follow the connection to mirror
# option: left to right, right to left
	pass
	

###############################################################################

# Other tools


def mirrorGeometry(*args, **keywords):
# Mirror geometry together with UV. The UV of character can be splited into a number of U regions.
# usage: select geometry which is present in the +x side and UVs in U=0.5-1 region (and U=1.5-2, U=2.5-3, ...)

	meshes = cmds.listRelatives(s=True, type="mesh", ni=True, f=True)

	if meshes == None:
		raise Exception, "No mesh selected"

	results = []
	for mesh in cmds.listRelatives(meshes, p=True, f=True):
		verticesInRegion = {}

		parent = cmds.listRelatives(mesh, p=True, f=True, pa=True)
		mesh1 = cmds.duplicate(mesh)
		mesh2 = cmds.duplicate(mesh)

		cmds.scale(-1, 1, 1, mesh2, r=True)

		# detect uv regions
		#		scan all vertices

		vertices = cmds.ls(cmds.polyListComponentConversion(mesh2, tuv=True), fl=True)
		for vertex in vertices:
			uv = cmds.polyEditUV(vertex, query=True)
			region = math.ceil(uv[0]) - 1
			if region < 0:
				region = 1
			if not verticesInRegion.has_key(region):
				verticesInRegion[region] = []
			verticesInRegion[region].append(vertex)

		#		choose vertices in regions
		#			flip uv upon middle of regions

		for region,vertices in verticesInRegion.iteritems():
			cmds.select(vertices, r=True)
			cmds.polyEditUV(pu=(region + 0.5), pv=0.5, su=-1, sv=1)

		#	combine objects and merge vertices

		combined = cmds.polyUnite(mesh1, mesh2, ch=False)
		if parent:
			results += cmds.parent(combined, parent)
		else:
			results += combined
		cmds.polyMergeVertex(d=0.005, ch=0)

	cmds.select(results, r=True)
	return results


def	connectAdjacentJoints(*args, **keywords):
# Connect rotation attributes of a joint to its immediate parent joint for double-joint setup at
# finger knuckles, knees, elbows, etc. Child joint is the driver because it's easier to select
# from viewport than the parent.
# usage: select joints

	attribute = attributeOptions()[0]		# TBD: get saved value
	if 'attribute' in keywords:
		attribute = keywords['attribute']

	target = targetOptions()[0]			# TBD: get saved value
	if 'target' in keywords:
		target = keywords['target']

	s = cmds.ls(sl=True, l=True, type='joint')
	if not s:
		raise Exception, "no joint selected"

	for j in s:
		if target == targetOptions()[0]:
			j1 = cmds.listRelatives(j, p=True, f=True, pa=True)
		else:
			j1 = cmds.listRelatives(j, f=True, pa=True)
		if j1:
			for p in j1:
				cmds.connectAttr(j+'.'+attribute, p+'.'+attribute, f=True)


def	attributeOptions():
	return [ "rotate", "rotateX", "rotateY", "rotateZ" ]


def	targetOptions():
	return [ "parent", "child" ]


def	skinWeights(x=None, export=None, f=None, fileName=None):
# Import/export skin weights from/to a file
# x/export: 0 for import, 1 for export
# f/fileName: filename under default project directory

	x = x or export

	if not (f or fileName):
		raise Exception, "Missing argument: fileName"
		
	if fileName:
		f = fileName
	
	obj = cmds.ls(sl=1)
	if not obj:
		raise Exception, "No object selected"

	obj = obj[0]

	node = None
	for n in cmds.listHistory(obj, f=0, bf=1):
		if cmds.nodeType(n) == 'skinCluster':
			node = n
			break
	if not node:
		raise Exception, "no skin cluster found"

	mode = "r"
	if x:
		mode = "w"
	f = open(cmds.internalVar(uwd=1) + f, mode)

	allTransforms = cmds.skinPercent(node, cmds.ls(cmds.polyListComponentConversion(obj, tv=1), fl=1), q=1, t=None)

	for vertex in cmds.ls(cmds.polyListComponentConversion(obj,tv=1), fl=1):
		if x:
			transforms = cmds.skinPercent(node, vertex, ib=1e-010, q=1, t=None)
			weights = cmds.skinPercent(node, vertex, ib=1e-010, q=1, v=1)
			s = ""
			for i in range(len(transforms)):
				s += str(weights[i])+"@"+transforms[i]+" "
			f.write(s+"\n")
		else:
			weights = {}
			for t in allTransforms:
				weights[t] = float(0)

			readWeights = f.readline().strip().split(" ")

			for i in readWeights:
				w = i.split("@")
				if w[1] in weights:
					weights[w[1]] = float(w[0])

			w = []
			for i in weights.iteritems():
				w.append(i)
			cmds.skinPercent(node, vertex, tv=w)

	f.close()
	

def	deleteNonCameraFacingPolygons():

	slist = OpenMaya.MSelectionList()
	OpenMaya.MGlobal.getActiveSelectionList( slist )

	cameraIt = OpenMaya.MItSelectionList( slist, OpenMaya.MFn.kCamera )
	cameraIt.reset()
	cameraDag = OpenMaya.MDagPath()

	while not cameraIt.isDone():
		if not cameraDag.isValid():
			cameraIt.getDagPath( cameraDag )
		else:
			raise Exception, "more than one camera selected"
		cameraIt.next()

	if not cameraDag.isValid():
		raise Exception, "no camera selected"

	cameraDirection = OpenMaya.MVector()
	cameraDirection = OpenMaya.MFnCamera( cameraDag ).viewDirection( OpenMaya.MSpace.kWorld )
	
	objDag = OpenMaya.MDagPath()
	meshFn = OpenMaya.MFnMesh()

	uiScriptUtil = OpenMaya.MScriptUtil()
	uiPtr = uiScriptUtil.asUintPtr()
	
	for i in range(slist.length()):
		slist.getDagPath(i, objDag )
		
		if objDag.hasFn( OpenMaya.MFn.kTransform ):
			objDag.numberOfShapesDirectlyBelow( uiPtr )
			shapes = int(uiScriptUtil.getUint( uiPtr ))

			oldObjDag = objDag
			for j in range( shapes ):
				objDag.extendToShapeDirectlyBelow( j )

				if objDag.hasFn( OpenMaya.MFn.kMesh ):
					meshFn.setObject( objDag )
					polygonNormal = OpenMaya.MVector()
					polygonIt = OpenMaya.MItMeshPolygon( objDag )
					polygonIt.reset()

					faces = []
					while not polygonIt.isDone():
						meshFn.getPolygonNormal( polygonIt.index(), polygonNormal, OpenMaya.MSpace.kWorld )
						if cameraDirection * polygonNormal > 0:
							faces.append(objDag.fullPathName()+'.f['+str(polygonIt.index())+']')
						polygonIt.next()
					cmds.polyDelFacet(faces)

				objDag = oldObjDag
	return


def	renameJointChain(jointChain):
# rename joint chain according to Paul Thuriot's naming convention
# set proper labels for FBIK generation

	if jointChain not in jointChainOptions():
		raise Exception, "Invalid joint chain: "+jointChain

	j = cmds.ls(sl=True)
	if cmds.nodeType(j) != "joint":
		raise Exception, "Selection is not a joint"

	sides = { "":0, "Lf":1, "Rt":2, "None":3 }
	typesFBIK = { "None":0, "Root":1, "Hip":2, "Knee":3, "Foot":4, \
		"Toe":5, "Spine":6, "Neck":7, "Head":8, "Collar":9, \
		"Shoulder":10, "Elbow":11, "Hand":12, "Finger":13, "Thumb":14, \
		"PropA":15, "PropB":16, "PropC":17, "Other":18, "Index Finger":19, \
		"Middle Finger":20, "Ring Finger":21, "Pinky Finger":22, "Extra Finger":23, "Big Toe":24, \
		"Index Toe":25, "Middle Toe":26, "Ring Toe":27, "Pinky Toe":28, "Extra Toe":29 }
	types = { "spine":[1,6], "neck":[7,8], "head":[8], "clavicle":[9,10,11,12,13], "arm":[10,11,12,13], "hand":[12,13], "leg":[2,3,4,5], "foot":[4,5], "thumb":[14], "index":[19], "middle":[20], "ring":[21], "pinky":[22] }

	name = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
	
	# find side by determining world position (multiply parent's world matrix with its translation)
	x = cmds.getAttr(j[0]+".tx")
	p = cmds.listRelatives(j, pa=True, p=True)
	if p:
		pmm = cmds.createNode("pointMatrixMult")
		cmds.connectAttr(p[0]+".worldMatrix[0]", pmm+".inMatrix")
		cmds.connectAttr(j[0]+".translate", pmm+".inPoint")
		x = cmds.getAttr(pmm+".outputX")
		cmds.delete(pmm)
	x = round(x, 10)
	side = ""
	if x > 0:
		side = "Lf"
	elif x < 0:
		side = "Rt"

	previous = None
	i = 0
	while j:
		cmds.setAttr(j[0]+".side", sides[side])
		if i < len(types[jointChain]):
			cmds.setAttr(j[0]+".type", types[jointChain][i])
		else:
			cmds.setAttr(j[0]+".type", types[jointChain][-1])
		previous = cmds.rename(j, jointChain+"J"+name[i]+side+"_1")
		j = cmds.listRelatives(previous, pa=True, type="joint")
		i += 1
		if i > len(name):
			raise Exception, "Too many joints"
	if previous:
		cmds.rename(previous, jointChain+"JEnd"+side+"_1")

	return


def	jointChainOptions():
	return [ "spine", "neck", "head", "clavicle", "arm", "hand", "leg", "foot", "thumb", "index", "middle", "ring", "pinky" ]


def	createVertexFollicles():
# usage: select vertices

	s = cmds.ls(sl=True, l=True, fl=True)
	if not s:
		raise Exception, "no selection"

	obj = cmds.listRelatives(cmds.ls(s, o=True, l=True), p=True, f=True)[0]
	cmds.select(cmds.polyListComponentConversion(s, tuv=True), r=True)
	dict = jc.helper.getVertexUV()

	follicles = []
	for i,uv in dict.iteritems():
		follicles.append(jc.helper.createFollicle(obj, uv))

	return follicles


def	createFolliclesOnMesh():
# Create follicles closest to the selected objects on the selected mesh, then move and parent them to the follicles
# usage: select objects (which can be locators or joints for skin bind purposes) and a polygon object

	meshes = cmds.listRelatives(s=True, type="mesh", ni=True, f=True)
	if meshes == None:
		raise Exception, "no mesh selected"
	mesh = cmds.listRelatives(meshes[-1], p=True, f=True)[0]
	def f(x): return x != mesh
	objs = filter(f, cmds.ls(sl=True, l=True))

	uvPairs = jc.helper.getUVAtPoint(objs, mesh)

	i = 0
	follicles = []
	for (u,v) in uvPairs:
		folTform = jc.helper.createFollicle(mesh, (u,v))
		#[x,y,z] = cmds.xform(folTform, q=True, t=True, a=True, ws=True)
		#cmds.move(x, y, z, objs[i], a=True, ws=True)
		#cmds.parent(objs[i], folTform)
		cmds.connectAttr(folTform + ".translate", objs[i] + ".translate", f=True)
		cmds.connectAttr(folTform + ".rotate", objs[i] + ".rotate", f=True)
		i += 1
		follicles.append(folTform)

	return follicles


def	createInfluenceObject(*args, **keywords):
# Create a skin patch to locally deformed the skin as influence object
# The patch can be deformed by blendShape or nCloth
# usage: select faces on a skinned object
# TBD: mirror (boolean), combine (boolean), layer
# TBD: need to preserve one skin cluster having no influence object (joint binded only, rigid shape w/o collision) 
# for the creation of attract to matching mesh constraint

	if 'influenceType' not in keywords:
		raise Exception, "missing argument influenceType"
	influenceType = keywords['influenceType']

	s = cmds.ls(sl=True, l=True)
	if not s:
		raise Exception, "no selection"
	faces = cmds.polyListComponentConversion(s, tf=True, internal=True)
	obj = cmds.listRelatives(cmds.ls(sl=True, o=True, l=True), p=True, f=True)
	sc = jc.helper.findTypeInHistory(obj, 'skinCluster')

	dup = cmds.duplicate(obj)
	def f(x): return dup[0] + re.search('\..*', x).group(0)
	faces = map(f, faces)
	cmds.polyChipOff(faces, ch=True, kft=True, dup=True, off=0)
	dup = cmds.listRelatives(list(set(cmds.ls(faces, o=True, l=True))), p=True, f=True)
	objs = cmds.polySeparate(dup, ch=False, rs=True)

	def f(x): return len(cmds.ls(cmds.polyListComponentConversion(x, tf=True), fl=True, l=True))
	face_counts = map(f, objs)
	cmds.delete(objs[face_counts.index(max(face_counts))])
	objs.pop(face_counts.index(max(face_counts)))

	jts = jc.helper.findTypeInHistory(sc, 'joint')
	for o in objs:
		if influenceType == "blendShape":
			dup = cmds.duplicate(o, rr=True)
			(x1,y1,z1, x2,y2,z2) = cmds.exactWorldBoundingBox(obj)
			cmds.move((x2-x1), 0, 0, dup, r=True)
		# bind objs to sc, then copy skin weights from obj to objs
		sc2 = cmds.skinCluster(jts, o)[0]
		cmds.copySkinWeights(ss=sc, ds=sc2, nm=True, sa="closestPoint", ia="closestJoint")
		if influenceType == "blendShape":
			bs = cmds.blendShape(dup, o, foc=True)
			cmds.setAttr(bs[0]+"."+dup[0], 1)
		elif influenceType == "nCloth":
			cmds.select(o, r=True)
			mel.eval("createNCloth 0;")
			ncloth = cmds.ls(sl=True)
			if ncloth:
				ncloth = ncloth[0]
				cmds.setAttr(ncloth+".inputMeshAttract", 2)
				cmds.select(o, r=True)
				jc.clothes.__updateNClothAttribute(cmds.ls(cmds.polyListComponentConversion(o, tv=True), fl=True), "inputMeshAttract", 0.03)
				cmds.select(cmds.polyListComponentConversion(o, te=True), r=True)
				cmds.polySelectConstraint(m=2, w=1)
				cmds.select(cmds.polyListComponentConversion(tv=True), r=True)
				cmds.polySelectConstraint(m=0, w=0)
				jc.clothes.__updateNClothAttribute(cmds.ls(sl=True, fl=True), "inputMeshAttract", 1)

	cmds.setAttr(sc+".useComponents", 1)
	def f((x,y)): return x-y
	for o in objs:
		cmds.skinCluster(sc, e=True, ug=True, dr=99, ps=0, ai=o)
		pts = []
		(x1,y1,z1, x2,y2,z2) = cmds.exactWorldBoundingBox(o)
		for v in cmds.ls(cmds.polyListComponentConversion(obj, tv=True), fl=True, l=True):
			outside = True
			(x,y,z) = cmds.pointPosition(v)
			if x>x1 and x<x2 and y>y1 and y<y2 and z>z1 and z<z2:
				for u in cmds.ls(cmds.polyListComponentConversion(o, tv=True), fl=True, l=True):
					zp = zip([x,y,z], cmds.pointPosition(u))
					(dx,dy,dz) = map(f, zp)
					if abs(dx) < 0.0001 and abs(dy) < 0.0001 and abs(dz) < 0.0001:
						outside = False
						break
			if outside:
				pts.append(v)
		if pts:
			cmds.skinPercent(sc, pts, tv=[o, 0])

	return


def	influenceTypes():
	return [ "None", "blendShape", "nCloth" ]


def	doMenu(do=True, parent=None):
	jc.menu.destroyMenu(__moduleName)

	if do:
		if parent:
			if isinstance(parent, jc.menu.subMenuItem):
				m = parent
			elif not isinstance(parent, types.StringType) or cmds.objectType(parent) != "floatingWindow":
				parent = None
		if not parent:
			m = jc.menu.createMenu(__moduleName, parent)
		
		i = jc.menu.commandItem(m, __moduleName+".createDeformer", "Create Deformer")
		jc.menu.listOption(i, "deformer", deformerOptions()[0], deformerOptions)

		i = jc.menu.commandItem(m, __moduleName+".copyPose", "Copy Pose")

		jc.menu.dividerItem(m)

		i = jc.menu.commandItem(m, __moduleName+".groupJoint", "Group Joint")

		i = jc.menu.commandItem(m, __moduleName+".createFacialControlRig", "Create Facial Control Rig")

		i = jc.menu.commandItem(m, __moduleName+".createFacialPoseNode", "Create Facial Pose Node")

		i = jc.menu.commandItem(m, __moduleName+".saveFacialPose", "Save Facial Pose")

		i = jc.menu.commandItem(m, __moduleName+".mirrorFacialPose", "Mirror Facial Pose")

		jc.menu.dividerItem(m)

		i = jc.menu.commandItem(m, __moduleName+".mirrorGeometry", "Mirror Geometry")

		i = jc.menu.commandItem(m, __moduleName+".connectAdjacentJoints", "Connect Adjacent Joints")
		jc.menu.listOption(i, "attribute", attributeOptions()[0], attributeOptions)
		jc.menu.listOption(i, "target", targetOptions()[0], targetOptions)

		i = jc.menu.commandItem(m, __moduleName+".skinWeights", "Import/Export Skin Weights")
		jc.menu.booleanOption(i, "export", True)
		jc.menu.stringOption(i, "file Name", "")

		i = jc.menu.commandItem(m, __moduleName+".deleteNonCameraFacingPolygons", "Delete Non Camera Facing Polygons")
		
		i = jc.menu.commandItem(m, __moduleName+".renameJointChain", "Rename Joint Chain")
		jc.menu.listOption(i, "jointChain", jointChainOptions()[0], jointChainOptions)

		i = jc.menu.commandItem(m, __moduleName+".createVertexFollicles", "Create Vertex Follicles")

		i = jc.menu.commandItem(m, __moduleName+".createFolliclesOnMesh", "Create Follicles on Mesh")

		i = jc.menu.commandItem(m, __moduleName+".createInfluenceObject", "Create Influence Object")
		jc.menu.listOption(i, "influence Type", influenceTypes()[0], "Influence Types")
