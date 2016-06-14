# clothes.py
# This is an implementation of a clothes making tool inside Maya.
#
# Installation:
# This file implements the module called jc.clothes.
# Under Maya script directory, create a directory called 'jc', put an empty file '__init__.py' and this file under there.
# Add PYTHONPATH to point to script directory in Maya.env.
# character.py, menu.py and helper.py are prerequisite.
#
# Author's website:
# http://sites.google.com/site/cgriders
#

import types, math, re, copy, csv, os, tempfile, traceback, sys
import maya.cmds as cmds
import maya.mel as mel
import maya.OpenMaya as om
import jc.character
import jc.menu
import jc.helper

# constants

__moduleName = "jc.clothes"
__destinationJoint = "jcdj"			# connect joint to destination joint
__pattern = "jcp"								# connect curve/button to pattern/garment
__locator = "jcl"								# connect curve/button to locator, locator(right) to locator
__patternCurve = "jcpc"					# connect joint to curve
__destinationCurve = "jcdc"			# connect curve to destination curve

__resolution = "jcr"						# float attribute on locator
__mirror = "jcm"								# boolean attribute on locator
__reverseNormal = "jcrn"				# boolean attribute on locator
__componentIndices = "jcci"			# multi-value attribute on curve
__twistRootLeft = "jctrl"				# float attribute on curve
__twistRootRight = "jctrr"			# float attribute on curve
__patternUV = "jcpuv"
__garmentUV = "jcguv"
__nearly_zero = 1.0e-10



def __findCurveLength__(curve, startU=0, endU=0):

	if startU==0 and endU==0:
		startU = cmds.getAttr(curve+".min")
		endU = cmds.getAttr(curve+".max")
	arclenDim = cmds.arcLengthDimension(curve+".u["+str(startU)+"]")
	startLen = cmds.getAttr(arclenDim+'.al')
	cmds.setAttr(arclenDim+'.upv', endU)
	endLen = cmds.getAttr(arclenDim+'.al')
	cmds.delete(cmds.listRelatives(arclenDim, p=True, f=True))

	return (endLen - startLen)


def __findU__(curve, length):

	startU = cmds.getAttr(curve+'.min')
	endU = cmds.getAttr(curve+'.max')
	arclenDim = cmds.arcLengthDimension(curve+".u["+str(endU)+"]")
	curveLen = cmds.getAttr(arclenDim+'.al')
	if curveLen < length:
		return endU

	uLen = curveLen
	u = endU
	count = 100
	while uLen != length and count > 0:
		u = startU + (u-startU)*length/uLen
		if u > endU:
			cmds.delete(cmds.listRelatives(arclenDim, p=True, f=True))
			raise Exception, "fail to find U (try to rebuild curve)"
		cmds.setAttr(arclenDim+".upv", u)
		uLen = cmds.getAttr(arclenDim+".al")
		count -= 1

	cmds.delete(cmds.listRelatives(arclenDim, p=True, f=True))

	return u


def __dist__(p1, p2):
	return math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2 + (p2[2] - p1[2]) ** 2)


def	getEdgePoints(curve, startVertex, division=10):
# output: list of points along the curve starting from the given vertex

	m = cmds.getAttr(curve+'.min')
	n = cmds.getAttr(curve+'.max')
	i = (m+n)/division
	pts = []
	for j in range(division+1):
		pts.append(cmds.pointOnCurve(curve, pr=m+i*j, p=True))
	if __dist__(startVertex, cmds.pointOnCurve(curve, pr=cmds.getAttr(curve+'.min'), p=True)) > __nearly_zero:
		pts.reverse()
	if math.fabs(pts[0][0]) < __nearly_zero:
		return pts[:-1]
	elif math.fabs(pts[-1][0]) < __nearly_zero:
		return pts[1:]
	return pts[1:-1]


def getPatternVertices(*args, **keywords):
# usage: select pattern curves
# - ends of curves must be touching
# output: list of vertices (as a tuple of curve and starting vertex) along anti-clockwise direction
# (it's not able to determine if it's along anti-clockwise direction for, say, sleeve pattern)
# if mirror is true, vertices at x=0 will be returned first

	mirror = True

	if 'mirror' in keywords:
		mirror = keywords['mirror']

	if args:
		cmds.select(args, r=True)
	curves = cmds.listRelatives(s=True, typ='nurbsCurve', f=True)
	if not curves:
		if not cmds.ls(sl=True, typ='nurbsCurve'):
			raise Exception, "no curve selected"
		else:
			curves = cmds.ls(sl=True, typ='nurbsCurve', l=True)
	curves = cmds.listRelatives(curves, p=True, typ='transform', f=True)

	curvesDict = {}
	for c in curves:
		mn = cmds.getAttr(c+'.min')
		mx = cmds.getAttr(c+'.max')
		curvesDict[c] = (cmds.pointOnCurve(c, pr=mn, p=True), cmds.pointOnCurve(c, pr=mx, p=True))

	curvesSorted = [curves[0]]
	if mirror:
		for c in curves:
			p0, p1 = curvesDict[c]
			if math.fabs(p0[0]) < __nearly_zero and math.fabs(p1[0]) < __nearly_zero:
				curvesSorted = [c]
				if p0[1] < p1[1]:
					curvesDict[c] = (p1, p0)
				break

	# sort the curves
	while len(curvesSorted) < len(curves):
		foundCurve = False
		p0, p1 = curvesDict[curvesSorted[-1]]
		for key, value in curvesDict.iteritems():
			if key != curvesSorted[-1]:
				q0, q1 = value
				if __dist__(p1, q0) < __nearly_zero:
					foundCurve = True
				elif __dist__(p1, q1) < __nearly_zero:
					foundCurve = True
					curvesDict[key] = (q1, q0)	# reverse the points in the dictionary
				if foundCurve:
					curvesSorted.append(key)
					break
		if not foundCurve and len(curvesSorted) < len(curves):
			raise Exception, "fail to find next connecting curve"

	vertices = []
	for c in curvesSorted:
		p0, p1 = curvesDict[c]
		vertices.append( (c, p0) )

	return vertices


def	createArcLengthDimension(*args):
# usage: select curves
# output: arcLengthDimension node is created, its attribute upv is connected to the curve's attribute max

	if args:
		cmds.select(args, r=True)
	curves = cmds.listRelatives(s=True, typ='nurbsCurve', f=True)
	if not curves:
		if not cmds.ls(sl=True, typ='nurbsCurve'):
			raise Exception, "no curve selected"
		else:
			curves = cmds.ls(sl=True, typ='nurbsCurve', l=True)
	curves = cmds.listRelatives(curves, p=True, typ='transform', f=True)

	for curve in curves:
		s = cmds.listRelatives(curve, s=True, typ='nurbsCurve', f=True)
		arcs = cmds.listConnections(s[0]+".max", sh=True)
		if arcs:
			for arc in arcs:
				if cmds.nodeType(arc) == 'arcLengthDimension':
					curve = None
					break
		if curve:
			dim = cmds.arcLengthDimension(curve+".u[0]")
			if dim:
				cmds.connectAttr(curve+".max", dim+".upv")


def	__selectBorderEdges(object):
	# there can be more than one border
	borderEdgesNum = set([])
	borderEdges = set([])
	for i in range(cmds.polyEvaluate(object, e=True)):
		if i in borderEdgesNum:
			continue
		edgesNum = cmds.polySelect(object, eb=i, ass=0, ns=True)
		if edgesNum:
			borderEdges |= set(cmds.ls(cmds.polySelect(object, eb=i, ass=True, ns=True), fl=True))
			borderEdgesNum |= set(edgesNum)
	return list(borderEdges)


def cutCurves(length, rebuildCurve=False):
# usage: select curves
#  length: length required
# output: curves of length as required, original curves would not be kept

	curves = cmds.listRelatives(ad=True, typ='nurbsCurve', f=True)
	if not curves:
		raise Exception, "no curve is selected"

	for curve in curves:
		if rebuildCurve:
			# Rebuild according to rebuild options (TBD)
			cmds.rebuildCurve(curve, ch=False, rpo=True, rt=4, end=1, kr=0, kcp=False, kep=False, kt=False, d=3, tol=0.01)

		curveLen = __findCurveLength__(curve)

		if curveLen < length:
			# to extend curve
			cmds.extendCurve(curve, d=length-curveLen, cos=False, ch=True, em=0, et=0, s=0, jn=True, rmk=True, rpo=True)
		else:
			# to shorten curve
			results = cmds.detachCurve(curve, p=__findU__(curve,length), ch=False, cos=True, rpo=True, k=(True,False))
			for s in results:
				if cmds.getAttr(s+".min") == cmds.getAttr(s+".max") == 0:
					cmds.delete(s)


def keyJoints(clearKeyframes=False):
# usage: select joint chains

	joints = cmds.ls(sl=True, typ='joint')
	if not joints:
		raise Exception, "no joint selected"

	for current in joints:
		if clearKeyframes:
			cmds.cutKey(current, cmds.listRelatives(current, ad=True, f=True, typ='joint'), at=("tx","ty","tz","rx","ry","rz","sx"), cl=True)
		cmds.setKeyframe(current, at='tx')
		cmds.setKeyframe(current, at='ty')
		cmds.setKeyframe(current, at='tz')
		cmds.setKeyframe(current, at='sx')
		j = cmds.listRelatives(current, c=True, typ='joint', f=True)
		while j:
			cmds.setKeyframe(current, at='rx')
			cmds.setKeyframe(current, at='ry')
			cmds.setKeyframe(current, at='rz')
			cmds.setKeyframe(current, at='sx')
			current = j[0]
			j = cmds.listRelatives(current, c=True, typ='joint', f=True)


def __compareJoints__():
# usage: select two joint chains

	joints = cmds.ls(sl=True, typ='joint')
	if not joints or len(joints) < 2:
		raise Exception, "two join chains must be selected"

	parent = cmds.listRelatives(joints[0], c=True, typ='joint', f=True)
	child = cmds.listRelatives(joints[1], c=True, typ='joint', f=True)
	while child and parent:
		if round(cmds.getAttr(parent[0]+'.tx'),10) != round(cmds.getAttr(child[0]+'.tx'),10):
			return False
		parent = cmds.listRelatives(parent, c=True, typ='joint', f=True)
		child = cmds.listRelatives(child, c=True, typ='joint', f=True)

	if not child and not parent:
		return True
	return False


def	__disableConstraints(object):
	constraints = cmds.ls(cmds.listHistory(object), typ=("aimConstraint","geometryConstraint","normalConstraint","orientConstraint","parentConstraint","pointConstraint","scaleConstraint","tangentConstraint"), fl=True)
	weights = {}
	for constraint in constraints:
		i = 0
		weightList = []
		while cmds.attributeQuery("w"+str(i), n=constraint, ex=True):
			weightList.append(cmds.getAttr(constraint+".w"+str(i)))
			cmds.setAttr(constraint+".w"+str(i), 0)
			i += 1
		weights[constraint] = weightList
	return weights


def	__restoreConstraints(object, weights):
	constraints = cmds.ls(cmds.listHistory(object), typ=("aimConstraint","geometryConstraint","normalConstraint","orientConstraint","parentConstraint","pointConstraint","scaleConstraint","tangentConstraint"), fl=True)
	for constraint in constraints:
		for i in range(len(weights[constraint])):
			cmds.setAttr(constraint+".w"+str(i), weights[constraint][i])


def matchJointsByOrient(setKeyframes):
# obsolete
# usage: select two joint chains and the second selected one will match the first
#  setKeyframes: boolean to indicate whether to set key at current time
# output: oriented joint chain

	if not __compareJoints__():
		raise Exception, "the joint chains do not match"

	joints = cmds.ls(sl=True, typ='joint')

	weights = __disableConstraints(joints[1])
	
	tl = cmds.pointConstraint(joints[1], q=True, tl=True)
	if tl:
		offset = cmds.pointConstraint(joints[1], q=True, o=True)
	cmds.pointConstraint(joints, offset=[ 0, 0, 0 ], weight=1)

	if cmds.attributeQuery("blendPoint1", n=joints[1], ex=True):
		cmds.setAttr(joints[1]+".blendPoint1", 1)
		
	if setKeyframes:
		cmds.setKeyframe(joints[1], at='tx')
		cmds.setKeyframe(joints[1], at='ty')
		cmds.setKeyframe(joints[1], at='tz')
	cmds.pointConstraint(joints, rm=True, mo=True)
	if tl:
		cmds.pointConstraint(joints[1], e=True, o=offset)
	
	__restoreConstraints(joints[1], weights)

	parent = cmds.listRelatives(joints[0], c=True, typ='joint', f=True)
	child = cmds.listRelatives(joints[1], c=True, typ='joint', f=True)
	while child and parent:
		cmds.orientConstraint(joints, offset=[ 0, 0, 0 ], weight=1)
		cmds.setAttr(joints[1]+'.sx', 1)
		if setKeyframes:
			cmds.setKeyframe(joints[1], at='rx')
			cmds.setKeyframe(joints[1], at='ry')
			cmds.setKeyframe(joints[1], at='rz')
			cmds.setKeyframe(joints[1], at='sx')
		cmds.orientConstraint(joints, rm=True, mo=True)
		joints[0] = parent[0]
		joints[1] = child[0]
		parent = cmds.listRelatives(joints[0], c=True, typ='joint', f=True)
		child = cmds.listRelatives(joints[1], c=True, typ='joint', f=True)


def __createIKs__(name):
# usage: select root joint
#  name: name prefix of IK handles
# output: list of IK handles

	joints = cmds.ls(sl=True, typ='joint')
	if not joints:
		raise Exception, "no joint selected"

	ikhandles = []
	for current in joints:
		ikhandles.append([])
		j = cmds.listRelatives(current, c=True, typ='joint', f=True)
		while j:
			ikhandles[len(ikhandles)-1].append(cmds.ikHandle(n=name, sj=current, ee=j[0]))
			current = j[0]
			j = cmds.listRelatives(current, c=True, typ='joint', f=True)

	return ikhandles


def __deleteIKs__():
# usage: select root joint

	joints = cmds.ls(sl=True, typ='joint')
	if not joints:
		raise Exception, "no joint selected"

	for current in joints:
		j = [ current ]
		while j:
			ik = cmds.ls(cmds.listConnections(j[0]+'.message', d=True), typ='ikHandle', fl=True)
			if ik:
				cmds.delete(ik)
			e = cmds.listRelatives(j[0], c=True, typ='ikEffector', f=True)
			if e:
				cmds.delete(e)
			j = cmds.listRelatives(j[0], c=True, typ='joint', f=True)




def matchJoints(stitchStartTime, stitchEndTime, twistRoot=0):
# usage: select a joint in the stitch joint chain, it will match its destination joint chain

	if not cmds.ls(sl=True, typ='joint'):
		raise Exception, "no joint selected"

	stitchJoint = cmds.ls(sl=True, typ='joint')[0]
	while cmds.listRelatives(stitchJoint, p=True, typ="joint"):
		stitchJoint = cmds.listRelatives(stitchJoint, p=True, typ="joint", f=True)[0]

	if not cmds.attributeQuery(__destinationJoint, n=stitchJoint, ex=True):
		raise Exception, "no destination joint"

	destinationJoint = cmds.listConnections(stitchJoint+"."+__destinationJoint)[0]
	cmds.select(destinationJoint, stitchJoint, r=True)
	cmds.currentTime(stitchStartTime)
	cmds.currentTime(stitchEndTime, update=False)
	matchJointsByIK(True, twistRoot)


def matchJointsByIK(setKeyframes, twistRoot=0):
# usage: select two joint chains, parent first, child second, child will match the parent
#  setKeyframes: boolean to indicate whether to set key at current time
# output: oriented joint chain

	if not __compareJoints__():
		raise Exception, "the joint chains do not match"

	joints = cmds.ls(sl=True, typ='joint')

	onLeft = True
	if cmds.xform(joints[1], q=True, ws=True, rp=True)[0] < 0:
		onLeft = False
	
	# create IKs on child
	cmds.select(joints[1], r=True);
	ikhandles = __createIKs__("ikHandle")

	weights = __disableConstraints(joints[1])
	
	tl = cmds.pointConstraint(joints[1], q=True, tl=True)
	if tl:
		offset = cmds.pointConstraint(joints[1], q=True, o=True)
	cmds.pointConstraint(joints, offset=[ 0, 0, 0 ], weight=1)

	if cmds.attributeQuery("blendPoint1", n=joints[1], ex=True):
		cmds.setAttr(joints[1]+".blendPoint1", 1)
		
	cmds.setKeyframe(joints[1], at='tx')
	cmds.setKeyframe(joints[1], at='ty')
	cmds.setKeyframe(joints[1], at='tz')
	cmds.pointConstraint(joints, rm=True, mo=True)
	if tl:
		cmds.pointConstraint(joints[1], e=True, o=offset)
	
	# twist root joint to fix weird rotation on some occasions
	if twistRoot != 0:
		ik = cmds.ls(cmds.listConnections(joints[1]+'.message', d=True), typ='ikHandle', fl=True)
		cmds.setAttr(ik[0]+'.twist', twistRoot)

	if cmds.attributeQuery(__patternCurve, n=joints[1], ex=True):
		patternCurve = cmds.listConnections(joints[1]+"."+__patternCurve)[0]
		if onLeft:
			if not cmds.attributeQuery(__twistRootLeft, n=patternCurve, ex=True):
				cmds.addAttr(patternCurve, sn=__twistRootLeft, at="float", dv=0, h=True)
			cmds.setAttr(patternCurve+"."+__twistRootLeft, twistRoot)
		else:
			if not cmds.attributeQuery(__twistRootRight, n=patternCurve, ex=True):
				cmds.addAttr(patternCurve, sn=__twistRootRight, at="float", dv=0, h=True)
			cmds.setAttr(patternCurve+"."+__twistRootRight, twistRoot)

	child = joints[1]
	parent = joints[0]
	while child and parent:
		parent = cmds.listRelatives(parent, c=True, typ='joint', f=True)
		ik = cmds.ls(cmds.listConnections(child+'.message', d=True), typ='ikHandle', fl=True)
		if ik and parent:
			parent = parent[0]
			ik = ik[0]
			#
			#	Setting translation is equivalent to making point constraint
			#	t = cmds.joint(parent, q=True, p=True)
			#	cmds.setAttr(ik+'.tx', t[0])
			#	cmds.setAttr(ik+'.ty', t[1])
			#	cmds.setAttr(ik+'.tz', t[2])
			#
			cmds.setAttr(child+'.sx', 1)
			cmds.pointConstraint(parent, ik, offset=[ 0, 0, 0 ], weight=1)
			cmds.setKeyframe(child, at='rx')
			cmds.setKeyframe(child, at='ry')
			cmds.setKeyframe(child, at='rz')
			cmds.setKeyframe(child, at='sx')
			cmds.pointConstraint(parent, ik, rm=True, mo=True)
		child = cmds.listRelatives(child, c=True, typ='joint', f=True)
		if child:
			child = child[0]

	cmds.select(joints[1], r=True)
	__deleteIKs__()

	__restoreConstraints(joints[1], weights)

	# fix exaggerated rotations
	l = cmds.listRelatives(joints[1], ad=True, type='joint', f=True)
	if not l: l = []
	for j in [joints[1]]+l:
		keys = cmds.keyframe(j+".r", q=True, name=True)
		if keys:
			for k in keys:
				timevalues = cmds.keyframe(k, q=True, tc=True, vc=True)
				if len(timevalues) == 4:
					if abs(timevalues[1] - timevalues[3]) > 180:
						if timevalues[1] > timevalues[3]:
							cmds.keyframe(k, e=True, a=True, t=(timevalues[2],timevalues[2]), vc=360+timevalues[3])
						else:
							cmds.keyframe(k, e=True, a=True, t=(timevalues[2],timevalues[2]), vc=timevalues[3]-360)


def flattenJoints(*args):

	if args:
		cmds.select(args, r=True)
	joints = cmds.ls(sl=True, typ='joint')
	if not joints:
		raise Exception, "no joint selected"

	for current in joints:
		j = cmds.listRelatives(current, c=True, typ='joint', f=True)
		while j:
			cmds.setAttr(current+'.rx', 0)
			cmds.setAttr(current+'.ry', 0)
			cmds.setAttr(current+'.rz', 0)
			cmds.setAttr(current+'.jox', 0)
			cmds.setAttr(current+'.joy', 0)
			cmds.setAttr(current+'.joz', 0)
			current = j[0]
			j = cmds.listRelatives(current, c=True, typ='joint', f=True)


def createStitchJoints(numberOfJoints, rebuildCurve=False):
# usage: select NURBS curves
#	numberOfJoints: number of joints between startU and endU
# turnOnPercentage option in pointOnCurve is not used because it's not actual percentage if U is not evenly distributed
# output: joint chains

	if numberOfJoints < 1:
		raise Exception, "number of subsegments cannot be smaller than 1"

	curves = cmds.listRelatives(s=True, typ='nurbsCurve', f=True)
	if not curves:
		raise Exception, "no curve is selected"

	joints = []

	for curve in curves:
		if rebuildCurve:
			# Rebuild according to rebuild options (TBD)
			cmds.rebuildCurve(curve, ch=False, rpo=True, rt=4, end=1, kr=0, kcp=False, kep=False, kt=False, d=3, tol=0.01)
		nLen = __findCurveLength__(curve)/numberOfJoints

		points = []
		points.append(cmds.pointOnCurve(curve, p=True, top=False, pr=cmds.getAttr(curve+".min")))

		for i in range(1, numberOfJoints):
			points.append(cmds.pointOnCurve(curve, p=True, top=False, pr=__findU__(curve, nLen*i)))

		points.append(cmds.pointOnCurve(curve, p=True, top=False, pr=cmds.getAttr(curve+".max")))

		# create joint chain

		cmds.select(cl=True)
		joint1 = cmds.joint(p=points[0])
		joints.append(joint1)

		del points[0]

		for p in points:
			joint2 = cmds.joint(p=p)
			cmds.joint(joint1, e=True, zso=True, oj='xyz', sao='yup')
			joint1 = joint2

	return joints


def	__findBorderVertices(curves, mirror=False, tolerance=0.01):
# the indexes of border vertices will be saved in the curves as a multi-value attribute

	if not isinstance(curves, types.ListType):
		curves = [ curves ]

	cmds.select(curves, r=True)
	curves = cmds.listRelatives(ad=True, typ='nurbsCurve', f=True)

	borderVertices = {}	# corresponding vertices of curves
	bbox = {}			# bounding box of curves
	curves2 = []		# curves whose corresponding vertices have not been found
	patterns = []		# all the related patterns or garment which there's only one

	for curve in curves:
		if cmds.attributeQuery(__pattern, n=curve, ex=True):
			pattern = cmds.listConnections(curve+"."+__pattern)
			if pattern:
				pattern = pattern[0]
				if pattern not in patterns:
					patterns.append(pattern)

				borderVertices[curve] = []
		
				if cmds.attributeQuery(__componentIndices, n=curve, ex=True):
					size = cmds.getAttr(curve+"."+__componentIndices, s=True)
					if size > 0:
						indices = cmds.getAttr(curve+"."+__componentIndices+"[:"+str(size-1)+"]")
						for index in indices:
							borderVertices[curve].append(pattern+".vtx["+str(index)+"]")
				else:
					cmds.addAttr(curve, sn=__componentIndices, m=True, at="long", h=True)
					curves2.append(curve)
					bbox[curve] = cmds.exactWorldBoundingBox(curve)

	if not cmds.pluginInfo('jcClothes',q=True,l=True):
		# this calculation would be replaced by plugin command jcBorderVerticesOnCurves upon garment creation
	
		# create circle of radius equal to tolerance
		c = cmds.circle(c=(0, 0, 0), nr=(0,0,1), sw=360, s=8, d=3, r=tolerance, ut=False, tol=0.01, ch=False)[0]
	
		indexReg = re.compile("\[([0-9]+)\]")
	
		vertices = []
		for pattern in patterns:
			vertices += cmds.ls(cmds.polyListComponentConversion(__selectBorderEdges(pattern), fe=True, tv=True), fl=True)
	
		for v in vertices:
			p = cmds.pointPosition(v)
			if not mirror and p[0] < 0:
				continue
			if mirror and p[0] < 0:
				p[0] = -p[0]
			for curve in curves2:
				# intersect curve and circle only if vertex is within bounding box of curve
				if p[0] < bbox[curve][0]-tolerance or p[0] > bbox[curve][3]+tolerance or p[1] < bbox[curve][1]-tolerance or p[1] > bbox[curve][4]+tolerance:
					continue
				cmds.move(p[0], p[1], p[2], c, a=True)
				if cmds.curveIntersect(c, curve, ud=True, d=(0,0,1), ch=False):
					borderVertices[curve].append(v)
					m = indexReg.search(v)
					if m:
						cmds.setAttr(curve+"."+__componentIndices+"["+str(cmds.getAttr(curve+"."+__componentIndices, s=True))+"]", int(m.group(1)))
					break
	
		cmds.delete(c)

	def f(x,y): return x+y
	return reduce(f, borderVertices.values())


def createStitch(*args, **keywords):
# usage: select two or three curves, destination curve first, pattern curve second and third
# output: joint list (destination joint in front)
# the resulting connections are:
# stitchJoint --> destinationJoint
# stitchJoint --> patternCurve (having attributes twistRootLeft, twistRootRight)

	# default values
	numberOfJoints			= 0			# 0 or missing: deduce from resolution
	rebuildDestinationCurve	= False
	mirror					= True		# take value from pattern if it doesn't exist
	stretch					= False
	bind					= True

	if 'numberOfJoints' in keywords:
		numberOfJoints = keywords['numberOfJoints']
	if 'rebuildDestinationCurve' in keywords:
		rebuildDestinationCurve = keywords['rebuildDestinationCurve']
	if 'mirror' in keywords:
		mirror = keywords['mirror']
	if 'stretch' in keywords:
		stretch = keywords['stretch']
	if 'bind' in keywords:
		bind = keywords['bind']

	if args:
		cmds.select(args, r=True)

	s = cmds.listRelatives(s=True, typ='nurbsCurve', f=True)
	if not s or len(s) < 2 or len(s) > 3:
		raise Exception, "2 or 3 curves must be selected"

	s = cmds.listRelatives(s, p=True, typ='transform', f=True)
	
	# check bounding box of 2nd and 3rd curves to ensure they're in z-plane
	bbox = cmds.exactWorldBoundingBox(s[1])
	if round(bbox[2],10) != 0 or round(bbox[5],10) != 0:
		raise Exception, cmds.ls(s[1])[0]+" is not in z-plane"
	if len(s) > 2:
		bbox = cmds.exactWorldBoundingBox(s[2])
		if round(bbox[2],10) != 0 or round(bbox[5],10) != 0:
			raise Exception, cmds.ls(s[2])[0]+" is not in z-plane"

	if not stretch:
		# pattern curves must be longer than destination curve
		if not cmds.arclen(s[0], ch=False) < cmds.arclen(s[1], ch=False):
			raise Exception, cmds.ls(s[1])[0]+" is shorter than "+cmds.ls(s[0])[0]
		if len(s) > 2 and not cmds.arclen(s[0], ch=False) < cmds.arclen(s[2], ch=False):
			raise Exception, cmds.ls(s[2])[0]+" is shorter than "+cmds.ls(s[0])[0]

	if not numberOfJoints:
		# deduce number of joints from resolution
		if not cmds.attributeQuery(__locator, n=s[1], ex=True):
			raise Exception, "unable to determine resolution"
		resolution = cmds.getAttr(cmds.listConnections(s[1]+"."+__locator)[0]+"."+__resolution)
		numberOfJoints = math.ceil(__findCurveLength__(s[0])*resolution/2)

	# create stitch joints for first curve
	cmds.select(s[0], r=True)
	joints = createStitchJoints(numberOfJoints, rebuildDestinationCurve)

	if not joints:
		raise Exception, "no joint is created"

	destinationJoint = joints[0]
	outputJoints = [(destinationJoint)]
	if 'mirror' not in keywords:
		mirror = cmds.getAttr(cmds.listConnections(s[1]+"."+__locator)[0]+"."+__mirror)
	if len(s) > 2:
		mirror = mirror and cmds.getAttr(cmds.listConnections(s[2]+"."+__locator)[0]+"."+__mirror)
	if mirror:
		cmds.mirrorJoint(destinationJoint, myz=True, mb=True)
		destinationJoint2 = cmds.ls(sl=True)[0]
		outputJoints[0] = (outputJoints[0], destinationJoint2)

	destinationLength = __findCurveLength__(s[0])

	borderEdges = []
	
	# for second and third curves, ie. pattern curves
	for patternCurve in s[1:]:
		# duplicate joint chain, flatten and move it to the start of the curve
		rootJt = cmds.duplicate(destinationJoint, rr=True, rc=True)[0]
		outputJoints.append((rootJt))
		flattenJoints(rootJt)
		p=cmds.pointOnCurve(patternCurve, p=True, top=False, pr=cmds.getAttr(patternCurve+".min"))
		eval("cmds.move("+str(p[0])+","+str(p[1])+","+str(p[2])+",a=1)")
		if mirror:
			rootJt2 = cmds.duplicate(destinationJoint2, rr=True, rc=True)[0]
			outputJoints[-1] = (outputJoints[-1], rootJt2)
			flattenJoints(rootJt2)
			eval("cmds.move("+str(-p[0])+","+str(p[1])+","+str(p[2])+",a=1)")

		patternLength = __findCurveLength__(patternCurve)
		lengthRatio = patternLength/destinationLength

		# match joint chain with the curve
		startU = float(0)
		rotationOffset = 360
		currentJt = rootJt
		nextJt = cmds.listRelatives(currentJt, c=True, typ='joint', f=True)
		if stretch:
			cmds.setAttr(currentJt+".sx", lengthRatio)
		if mirror:
			currentJt2 = rootJt2
			nextJt2 = cmds.listRelatives(currentJt2, c=True, typ='joint', f=True)
			if stretch:
				cmds.setAttr(currentJt2+".sx", lengthRatio)
		while nextJt:
			nextJt = nextJt[0]
			if mirror:
				nextJt2 = nextJt2[0]

			# create circle at current joint and of radius equal to length of joint and with 360 sections (=degree)
			c = cmds.circle(c=cmds.joint(currentJt, q=True, a=True, p=True), nr=(0,0,1), sw=360, s=360, d=3, r=cmds.getAttr(nextJt+".tx")*cmds.getAttr(currentJt+".sx"), ut=False, tol=0.01, ch=False)[0]

			# intersect curve with circle
			ci = cmds.curveIntersect(patternCurve, c, ud=True, d=(0,0,1), ch=True)
			p1 = list(cmds.getAttr(ci+".p1")[0])	# intersection points on curve
			p2 = list(cmds.getAttr(ci+".p2")[0])	# intersection points on circle (equal to degree)

			# clean up
			cmds.delete(c)
			cmds.delete(ci)

			# look for the intersection point further along the curve from current joint position (startU)
			while p1 and min(p1) <= startU:
				i = p1.index(min(p1))
				del p1[i]
				del p2[i]

			if not p1:
				raise Exception, "can't determine rotation of last joint, pattern curve too short"

			# set rotation of current joint for the choosen intersection point on circle
			cmds.setAttr(currentJt+".rz", min(p2)-rotationOffset+90)
			if mirror:
				cmds.setAttr(currentJt2+".rz", -(min(p2)-rotationOffset+90))

			# prepare for next iteration
			startU = min(p1)
			rotationOffset += cmds.getAttr(currentJt+".rz")
			currentJt = nextJt
			nextJt = cmds.listRelatives(nextJt, c=True, typ='joint', f=True)
			if stretch:
				cmds.setAttr(currentJt+".sx", lengthRatio)
			if mirror:
				currentJt2 = nextJt2
				nextJt2 = cmds.listRelatives(nextJt2, c=True, typ='joint', f=True)
				if stretch:
					cmds.setAttr(currentJt2+".sx", lengthRatio)
				
		cmds.addAttr(rootJt, sn=__destinationJoint, at="message", h=True)
		cmds.connectAttr(destinationJoint+".message", rootJt+"."+__destinationJoint)
		if mirror:
			cmds.addAttr(rootJt2, sn=__destinationJoint, at="message", h=True)
			cmds.connectAttr(destinationJoint2+".message", rootJt2+"."+__destinationJoint)

		cmds.addAttr(rootJt, sn=__patternCurve, at="message", h=True)
		cmds.connectAttr(patternCurve+".message", rootJt+"."+__patternCurve)
		if not cmds.attributeQuery(__twistRootLeft, n=patternCurve, ex=True):
			cmds.addAttr(patternCurve, sn=__twistRootLeft, at="float", dv=0, h=True)
		if mirror:
			cmds.addAttr(rootJt2, sn=__patternCurve, at="message", h=True)
			cmds.connectAttr(patternCurve+".message", rootJt2+"."+__patternCurve)
			if not cmds.attributeQuery(__twistRootRight, n=patternCurve, ex=True):
				cmds.addAttr(patternCurve, sn=__twistRootRight, at="float", dv=0, h=True)

		if bind:
			if cmds.attributeQuery(__pattern, n=cmds.listRelatives(patternCurve, s=True, f=True)[0], ex=True):
				pattern = cmds.listConnections(patternCurve+"."+__pattern)
				if pattern:
					pattern = pattern[0]
	
					# bind pattern to stitch
					ncloth = cmds.ls(cmds.listHistory(pattern), typ="nCloth")
					inputMesh = pattern
					if ncloth:
						inputMesh = cmds.listConnections(ncloth[0]+".inputMesh", sh=True)[0]
		
					sc = cmds.ls(cmds.listHistory(inputMesh), typ="skinCluster")
					if not sc:
						if cmds.getAttr(inputMesh+".intermediateObject"):
							cmds.setAttr(inputMesh+".intermediateObject", 0)
							cmds.skinCluster(rootJt, inputMesh)
							cmds.setAttr(inputMesh+".intermediateObject", 1)
						else:
							cmds.skinCluster(rootJt, inputMesh)
					else:
						cmds.skinCluster(inputMesh, e=True, ai=rootJt)
						cmds.skinCluster(inputMesh, e=True, ai=cmds.listRelatives(rootJt, ad=True, f=True))

					borderVertices = __findBorderVertices(patternCurve, mirror)
					if borderVertices:
						borderEdges += list(set(cmds.ls(cmds.polyListComponentConversion(borderVertices, te=1), fl=1)) - set(cmds.ls(cmds.polyListComponentConversion(borderVertices, te=1, bo=1), fl=1)))
						cmds.select(pattern, r=True)
						__updateNClothAttribute(borderVertices, "inputMeshAttract", 1)

					if mirror:
						cmds.skinCluster(inputMesh, e=True, ai=rootJt2)
						cmds.skinCluster(inputMesh, e=True, ai=cmds.listRelatives(rootJt2, ad=True, f=True))

		if cmds.attributeQuery(__destinationCurve, n=patternCurve, ex=True):
			cmds.deleteAttr(patternCurve, at=__destinationCurve)
		cmds.addAttr(patternCurve, sn=__destinationCurve, at="message", h=True)
		cmds.connectAttr(s[0]+".message", patternCurve+"."+__destinationCurve, f=True)

	return outputJoints


def	dxc883(s):
	return b64decode(s)


def	createWeldConstraint(*args, **keywords):
# there're two kinds of constraints: weld and point-to-surface
# weld constraint is to weld edges of two patterns
# point-to-surface constraint is to weld edges of one pattern to the surface or another pattern
# usage: select curves (pattern curves) and optionally one garment when the patterns are still flat in XY-plane

	if args:
		cmds.select(args, r=True)

	def	findCurves(x):
		if cmds.listRelatives(x, s=True, ni=True, typ='nurbsCurve'):
			return True
		return False

	def	findGarment(x):
		if cmds.listRelatives(x, s=True, ni=True, typ='mesh') and (cmds.ls(cmds.listHistory(x), typ='nCloth') or cmds.ls(cmds.listHistory(x, f=True), typ='nRigid')):
			return True
		return False

	curves = filter(findCurves, cmds.ls(sl=True, l=True))
	garment = filter(findGarment, cmds.ls(sl=True, l=True))
	if garment:
		garment = garment[0]
	
	if not curves:
		raise Exception, "no curve selected"

	unmirroredCurves = curves
	borderVertices = []

	def mirror(x):
		if cmds.attributeQuery(__locator, n=x, ex=True):
			return cmds.getAttr(cmds.listConnections(x+"."+__locator)[0]+"."+__mirror)
		return False
	mirroredCurves = filter(mirror, cmds.listRelatives(curves, s=True, f=True))
	if mirroredCurves:
		mirroredCurves = cmds.listRelatives(mirroredCurves, p=True, f=True)
		borderVertices = __findBorderVertices(mirroredCurves, True)
		unmirroredCurves = list(set(curves) - set(cmds.ls(mirroredCurves)))
	if unmirroredCurves:
		borderVertices += __findBorderVertices(unmirroredCurves, False)

	if borderVertices:
		borderEdges = list(set(cmds.ls(cmds.polyListComponentConversion(borderVertices, te=1), fl=1)) - set(cmds.ls(cmds.polyListComponentConversion(borderVertices, te=1, bo=1), fl=1)))
		if garment:
			cmds.select(cmds.polyListComponentConversion(borderEdges, tv=True), r=True)
			cmds.select(garment, add=True)
			if cmds.ls(cmds.listHistory(garment, f=True), typ='nRigid'):
				__createWeldConstraint('pointToSurface', 0)
			else:
				__createWeldConstraint('pointToSurface')
		else:
			cmds.select(borderEdges, r=True)
			__createWeldConstraint('weldBorders')


def	__createWeldConstraint(type, restLengthMethod=1):
	mel.eval("performCreateDynamicConstraint 0 \""+type+"\";")
	nconstraint = cmds.ls(sl=True)
	if nconstraint:
		nconstraint = nconstraint[0]
		cmds.setAttr(nconstraint+".enable", 0)
		cmds.setAttr(nconstraint+".restLengthMethod", restLengthMethod)
		cmds.setAttr(nconstraint+".excludeCollisions", 1)
		cmds.setAttr(nconstraint+".damp", 1)
		cmds.setAttr(nconstraint+".maxDistance", 0.1)


def createPattern(*args, **keywords):
# usage: select NURBS curves which form the closed boundary of a pattern, 
#   a locator which is inside the boundary of the pattern,
#   the order of selection is irrelevant
#	The operation would be pivoted upon the lower left-hand corner
#	mirror: boolean value for mirror operation which can only be performed upon y-axis, jc.character required
#   resolution: square per cm, pattern will be composed of squares of size 1/resolution cm
# output: polygon patch and its mirror, mirrored locator

	if set(keywords.keys()) != set(['mirror','resolution','reverseNormal']):
		raise Exception, "argument error"
	mirror 			= keywords['mirror']
	resolution 		= keywords['resolution']
	reverseNormal 	= keywords['reverseNormal']
	
	if resolution <= 0:
		raise Exception, "resolution must be large than 0"

	if args:
		cmds.select(args, r=True)

	curves = cmds.listRelatives(ad=True, typ='nurbsCurve', f=True)
	locator = cmds.listRelatives(ad=True, typ='locator', f=True)
	if locator:
		locator = locator[0]
	else:
		raise Exception, "no locator is selected"

	# put pattern properties into locator
	if not cmds.attributeQuery(__resolution, n=locator, ex=True):
		cmds.addAttr(locator, sn=__resolution, at="float", h=True)
	cmds.setAttr(locator+"."+__resolution, resolution)
	if not cmds.attributeQuery(__reverseNormal, n=locator, ex=True):
		cmds.addAttr(locator, sn=__reverseNormal, at="bool", h=True)
	cmds.setAttr(locator+"."+__reverseNormal, reverseNormal)
	if not cmds.attributeQuery(__mirror, n=locator, ex=True):
		cmds.addAttr(locator, sn=__mirror, at="bool", h=True)
	cmds.setAttr(locator+"."+__mirror, mirror)

	# move transform scale to local scale of locator
	# this is to prevent extra transforms added over joints when they are being parented under locator
	locatorT = cmds.listRelatives(locator, p=True, f=True)[0]
	if not cmds.getAttr(locatorT+".s", l=True):
		transformScale = cmds.getAttr(locatorT+".s")[0]
		cmds.setAttr(locatorT+".s", 1, 1, 1)
		cmds.setAttr(locatorT+".s", l=True)
		cmds.setAttr(locator+".los", transformScale[0], transformScale[1], transformScale[2])

	# check if the curves are closed or intersecting
	if curves:
		if len(curves) > 1:
			for curve in curves:
				count = 0
				for curve1 in curves:
					if curve == curve1:
						continue
					s = cmds.curveIntersect(curve, curve1)
					if s:
						count += 1
					if count > 1:
						break
				if count < 1:
					raise Exception, "the curves are not closed"
		elif cmds.getAttr(curves[0]+'.form') < 1:
				raise Exception, "the curve is not closed"


	# create NURBS plane

	bbox = cmds.exactWorldBoundingBox(curves, ii=True)

	if round(bbox[0],10) == round(bbox[3],10):
		axis = [ 1, 0, 0 ]
		maxW = bbox[5]
		minW = bbox[2]
		maxL = bbox[4]
		minL = bbox[1]
	elif round(bbox[1],10) == round(bbox[4],10):
		axis = [ 0, 1, 0 ]
		maxW = bbox[3]
		minW = bbox[0]
		maxL = bbox[5]
		minL = bbox[2]
	elif round(bbox[2],10) == round(bbox[5],10):
		axis = [ 0, 0, 1 ]
		maxW = bbox[3]
		minW = bbox[0]
		maxL = bbox[4]
		minL = bbox[1]
	else:
		raise Exception, "the curves are not in a plane"

	width = math.ceil(maxW) - math.floor(minW)
	length = math.ceil(maxL)- math.floor(minL)

	if width > length:
		scale = 0.5
		length = width
	else:
		scale = width / length
		width = length
	if scale < 0.5:
		scale = 1

	if round(bbox[0],10) == round(bbox[3],10):
		pivot = [ bbox[0], minW+width/2, minL+length/2 ]
	elif round(bbox[1],10) == round(bbox[4],10):
		pivot = [ minW+width/2, bbox[1], minL+length/2 ]
	elif round(bbox[2],10) == round(bbox[5],10):
		pivot = [ minW+width/2, minL+length/2, bbox[2] ]

	planeNURBS = cmds.nurbsPlane(p=pivot, ax=axis, w=width, lr=1, d=3, u=math.ceil(width*resolution), v=math.ceil(length*resolution), ch=0)
	bbox1 = cmds.exactWorldBoundingBox(planeNURBS)

	# project curves onto NURBS plane

	projectCurves = []
	for curve in curves:
		try:
			s = cmds.projectCurve(curve, planeNURBS, ch=False, rn=False, un=False, tol=0.01)
			projectCurves = projectCurves + s
		except:
			continue
	if not projectCurves:
		raise Exception, "fail to project curves"

	# find uv position of locator within the NURBS plane
	
	lowerLeft = cmds.pointOnSurface(planeNURBS, p=True, u=0, v=0)
	upperRight = cmds.pointOnSurface(planeNURBS, p=True, u=1, v=1)
	p = cmds.pointPosition(locator, w=True)
	u = (p[0] - lowerLeft[0])/(upperRight[0] - lowerLeft[0])
	v = (p[1] - lowerLeft[1])/(upperRight[1] - lowerLeft[1])
	if u < 0 or u > 1 or v < 0 or v > 1:
		raise Exception, "locator falls outside the NURBS plane"

	# trim, convert into polygon and delete NURBS plane

	cmds.trim(planeNURBS, projectCurves, ch=0, o=1, rpo=1, lu=u, lv=v)
	pattern = cmds.nurbsToPoly(planeNURBS, mnd=1, ch=0, f=2, pt=1, pc=200, chr=0.1, ft=0.01, mel=0.001, d=0.1, ut=3, un=1, vt=3, vn=1, uch=0, ucr=0, cht=0.01, es=0, ntr=0, mrt=0, uss=1)[0]
	bbox2 = cmds.exactWorldBoundingBox(pattern)
	cmds.delete(planeNURBS)

	if abs(bbox1[0]-bbox2[0]) < 0.01 and \
		abs(bbox1[1]-bbox2[1]) < 0.01 and \
		abs(bbox1[2]-bbox2[2]) < 0.01 and \
		abs(bbox1[3]-bbox2[3]) < 0.01 and \
		abs(bbox1[4]-bbox2[4]) < 0.01 and \
		abs(bbox1[5]-bbox2[5]) < 0.01:
		raise Exception, "fail to create pattern due to trimming, check curves, or adjust their positions in space"

	if reverseNormal:
		cmds.polyNormal(pattern, nm=4, ch=False)
		cmds.select(pattern, r=True)

	locatorRt = None

	if mirror:
		cmds.select(cmds.ls(cmds.polyListComponentConversion(pattern, tuv=True), fl=True), r=True)
		cmds.polyEditUV(pu=0, pv=0, su=scale, sv=scale)
		cmds.polyEditUV(u=0.5, v=0)

		cmds.select(pattern, r=True)
		s = jc.character.mirrorGeometry()[0]
		cmds.delete(pattern)
		pattern = s

		# mirror locator only if it doesn't exist and locator is on the left (not in the middle)
		plugs = cmds.listConnections(locator+".message", t='locator', p=True)
		p = cmds.pointPosition(locator, w=True)
		if (not plugs or __locator not in plugs[0]) and round(p[0],10) > 0:
			locatorRt = cmds.listRelatives(cmds.duplicate(locator, n=cmds.listRelatives(locator, p=True)[0].replace('Lf','Rt'))[0], s=True)[0]
			cmds.move(-p[0], p[1], p[2], locatorRt, a=True, ws=True)
			cmds.addAttr(locatorRt, sn=__locator, at="message", h=True)
			cmds.connectAttr(locator+".message", locatorRt+"."+__locator, f=True)
			expr  = "RIGHT.tx=-1*LEFT.tx;\rRIGHT.ty=LEFT.ty;\rRIGHT.tz=LEFT.tz;\r"
			expr += "RIGHT.rx=LEFT.rx;\rRIGHT.ry=-1*LEFT.ry;\rRIGHT.rz=-1*LEFT.rz;\r"
			expr += "RSHAPE.lsx=LSHAPE.lsx;\rRSHAPE.lsy=LSHAPE.lsy;\rRSHAPE.lsz=LSHAPE.lsz;"
			expr = expr.replace("RIGHT", cmds.listRelatives(locatorRt, p=True)[0])
			expr = expr.replace("LEFT", cmds.listRelatives(locator, p=True)[0])
			expr = expr.replace("RSHAPE", locatorRt)
			expr = expr.replace("LSHAPE", locator)
			cmds.expression(s=expr)

	cmds.polyUVSet(pattern, cr=True, uvs=__patternUV)
	cmds.polyProjection(cmds.polyListComponentConversion(pattern, tf=True), ch=False, kir=True, md="z", uvs=__patternUV)
	cmds.polyUVSet(pattern, cp=True, uvs=__patternUV, nuv="map1")

	for curve in curves:
		if not cmds.attributeQuery(__pattern, n=curve, ex=True):
			cmds.addAttr(curve, sn=__pattern, at="message", h=True)
		cmds.connectAttr(pattern+".message", curve+"."+__pattern, f=True)

		if cmds.attributeQuery(__locator, n=curve, ex=True):
			cmds.deleteAttr(curve, at=__locator)
		cmds.addAttr(curve, sn=__locator, at="message", h=True)
		cmds.connectAttr(locator+".message", curve+"."+__locator, f=True)

		if cmds.attributeQuery(__componentIndices, n=curve, ex=True):
			cmds.deleteAttr(curve, at=__componentIndices)

	cmds.select(pattern, r=True)
	return pattern
	

def	getNClothPresetsCallback():
	return jc.helper.getPresets("nCloth")


def	createGarment(*args, **keywords):
# usage: select patterns (polygon objects)
#	Combine all patterns, rebuild UV map, preserve connections to jcPattern and create nCloth.

	prefix = None
	nClothPreset = None

	if 'prefix' in keywords:				prefix = keywords['prefix']
	if 'nClothPreset' in keywords:	nClothPreset = keywords['nClothPreset']

	if args:
		cmds.select(args, r=True)

	patterns = cmds.listRelatives(typ="mesh", f=True)
	if not patterns or (patterns and len(patterns) < 1):
		raise Exception, "not enough mesh selection"
	
	# check if they're planar

	bbox = cmds.exactWorldBoundingBox(cmds.ls(sl=True), ii=True)

	if round(bbox[0],10) == round(bbox[3],10):
		md = "x"
	elif round(bbox[1],10) == round(bbox[4],10):
		md = "y"
	elif round(bbox[2],10) == round(bbox[5],10):
		md = "z"
	else:
		raise Exception, "objects are not planar"
	
	curvePlugs = []
	follicles = []
	for m in patterns:
		plugs = cmds.listConnections(cmds.listRelatives(m, p=True, f=True)[0]+".message", s=False, d=True, p=True)
		if not plugs:
			raise Exception, "\""+cmds.listRelatives(m, p=True, f=True)[0]+"\" is not a pattern"
		curvePlugs += plugs
		f = cmds.listConnections(cmds.listRelatives(m, p=True, f=True)[0]+".outMesh", s=False, d=True, p=False)
		if f:
			follicles += cmds.listRelatives(f, type='follicle', f=True)

	pattern = cmds.listRelatives(patterns[0], p=True, f=True)[0]
	if len(patterns) > 1:
		pattern = cmds.polyUnite(patterns, ch=False)[0]
		for curvePlug in curvePlugs:
			if __pattern in curvePlug:
				cmds.connectAttr(pattern+".message", curvePlug, f=True)

	if prefix:
		pattern = cmds.rename(pattern, prefix+"S_#")

	if __patternUV not in cmds.polyUVSet(pattern, q=True, auv=True):
		cmds.polyUVSet(pattern, cr=True, uvs=__patternUV)
	cmds.polyProjection(cmds.polyListComponentConversion(pattern, tf=True), ch=False, kir=True, md=md, uvs=__patternUV)
	cmds.polyUVSet(pattern, cp=True, uvs=__patternUV, nuv="map1")

	if cmds.pluginInfo('jcClothes',q=True,l=True):
		cmds.jcBorderVerticesOnCurves(pattern)
	else:
		#raise Exception, "plugin jcClothes has not been loaded"
		pass	# if plugin is not present __findBorderVertices would do the job

	mel.eval("createNCloth 0;")
	ncloth = cmds.ls(sl=True)
	if ncloth:
		ncloth = ncloth[0]
		if nClothPreset and nClothPreset != getNClothPresetsCallback()[0]:
			jc.helper.applyAttrPreset(ncloth, nClothPreset)
		cmds.setAttr(ncloth+".inputMeshAttract", 2)
		if prefix:
			ncloth = cmds.rename(cmds.listRelatives(ncloth, p=True), prefix+"NC_#")
		cmds.select(pattern, r=True)
		__updateNClothAttribute(cmds.ls(cmds.polyListComponentConversion(pattern ,tv=True), fl=True), "inputMeshAttract", 0)

		pattern = cmds.listConnections(ncloth+".outputMesh")[0]
		bbox = cmds.exactWorldBoundingBox(pattern)
		w = bbox[3] - bbox[0]
		h = bbox[4] - bbox[1]
		m = max(w,h)
		center = [ bbox[0] + w/2, bbox[1] + h/2 ]
		p1 = [ center[0] - m/2, center[1] - m/2 ]
		p2 = [ center[0] + m/2, center[1] + m/2 ]
		for f in follicles:
			t = cmds.listRelatives(f, p=True, f=True)[0]
			x,y,z = cmds.xform(t, q=True, t=True)
			if x > p1[0] and x < p2[0] and y > p1[1] and y < p2[1]:
				u = (x - p1[0]) / m
				v = (y - p1[1]) / m
				try:
					cmds.connectAttr(pattern+'.worldMatrix', f+'.inputWorldMatrix', f=True)
				except:
					pass
				cmds.connectAttr(pattern+'.outMesh', f+'.inputMesh', f=True)
				cmds.setAttr(f+'.pu', u)
				cmds.setAttr(f+'.pv', v)
				cmds.setAttr(f+'.msn', __patternUV, type='string')

	return pattern


def	attachButtons(*args, **keywords):
# usage: select garment and buttons (meshes)
# two types of button: follicle and nCloth
# the front side of the button should be facing positive Z directions

	if 'buttonType' not in keywords.keys():
		raise Exception, "argument error"

	buttonType = keywords['buttonType']

	nClothPreset = None
	if 'nClothPreset' in keywords.keys():
		nClothPreset = keywords['nClothPreset']

	groupName = None
	if 'groupName' in keywords.keys():
		groupName = keywords['groupName']

	if args:
		cmds.select(args, r=True)

	buttons = cmds.listRelatives(cmds.ls(sl=True, l=True), type='mesh', f=True)
	if not buttons:
		raise Exception, "no mesh selected"

	buttons = list(set(cmds.listRelatives(buttons, p=True, f=True)))

	garment = None
	for button in buttons:
		garment = jc.helper.findTypeInHistory(button, "nCloth")
		if garment:
			garment = button
			del buttons[buttons.index(button)]
			break
	if not garment:
		raise Exception, "no garment is selected"

	grp = None
	if groupName:
		cmds.group(em=True, w=True)
		grp = jc.helper.batchRename(groupName)

	for button in buttons:
		f = cmds.createNode('follicle')
		t = cmds.listRelatives(f, p=True)[0]
		cmds.connectAttr(garment+'.worldMatrix', f+'.inputWorldMatrix')
		cmds.connectAttr(garment+'.outMesh', f+'.inputMesh')
		cmds.connectAttr(f+'.outTranslate', t+'.translate')
		cmds.connectAttr(f+'.outRotate', t+'.rotate')
		np = cmds.nearestPointOnMesh(garment, ip=cmds.xform(button, q=True, ws=True, t=True))
		cmds.setAttr(f+'.pu', cmds.getAttr(np+'.u'))
		cmds.setAttr(f+'.pv', cmds.getAttr(np+'.v'))
		#u,v = cmds.polyEditUV(cmds.polyListComponentConversion(vtx, tuv=True), q=True)
		#cmds.setAttr(f+'.pu', u)
		#cmds.setAttr(f+'.pv', v)
		cmds.connectAttr(t+".translate", button+".translate", f=True)
		cmds.connectAttr(t+".rotate", button+".rotate", f=True)
		ncloth = None
		if buttonType != buttonOptions()[0]:
			cmds.delete(t)
			cmds.select(button, r=True)
			mel.eval("createNCloth 0;")
			ncloth = cmds.ls(sl=True)
			if ncloth:
				ncloth = ncloth[0]
				if nClothPreset and nClothPreset != getNClothPresetsCallback()[0]:
					jc.helper.applyAttrPreset(ncloth, nClothPreset)
				cmds.select(garment, r=True)
				# find a vertex on button
				cmds.select(button, add=True)
				mel.eval("createNConstraint pointToSurface 0")
				constraint = cmds.ls(sl=True)
		if grp:
			if cmds.objExists(t):
				cmds.parent(t, grp)
			elif ncloth:
				cmds.parent(cmds.listRelatives(ncloth, p=True), grp)
				cmds.parent(cmds.listRelatives(constraint, p=True), grp)


def buttonOptions():
  return [ "Follicle", "nCloth" ]


def rebuildUV(*args):
# usage: select garments, UV maps will be rebuilt by projection on their rest shapes

	if args:
		cmds.select(args, r=True)

	ncloths = []

	for garment in cmds.ls(sl=True):
		nc = jc.helper.findTypeInHistory(garment, type="nCloth")
		if not nc:
			raise Exception, "selected object is not an ncloth object"
		ncloths.append(nc)

	garments = []

	for nc in ncloths:
		restShape = cmds.listConnections(nc+".restShapeMesh", sh=True)
		inputMesh = cmds.listConnections(nc+".inputMesh", sh=True)
		if restShape:
			cmds.setAttr(restShape[0]+".intermediateObject", 0)
			garments.append({ 'restShape':restShape[0], 'inputMesh':inputMesh[0], 'faces':cmds.polyListComponentConversion(restShape[0], tf=True)[0] })
		else:
			meshes = cmds.ls(cmds.listHistory(inputMesh), type='mesh')
			for mesh in meshes:
				if cmds.ls(cmds.listHistory(mesh), type='mesh') == [ mesh ]:
					cmds.setAttr(mesh+".intermediateObject", 0)
					garments.append({ 'restShape':mesh, 'inputMesh':inputMesh[0], 'faces':cmds.ls(cmds.polyListComponentConversion(mesh, tf=True), fl=True) })
					break

	faces = []
	for g in garments:
		faces += g['faces']
	cmds.polyProjection(faces, ch=False, kir=True, type="Planar", md="z", uvs="map1")

	for g in garments:
		i = cmds.getAttr(g['inputMesh']+".intermediateObject")
		cmds.setAttr(g['inputMesh']+".intermediateObject", 0)
		# bug in component-based (spa=4) transferAttrubutes()
		#cmds.transferAttributes(g['restShape'], g['inputMesh'], uvs=2, spa=4)
		#cmds.transferAttributes(g['restShape'], g['inputMesh'], uvs=2, spa=0)
		cmds.setAttr(g['inputMesh']+".intermediateObject", i)
		cmds.setAttr(g['restShape']+".intermediateObject", 1)


def matchUVScale():
# obsolete
# usage: select polygon objects, their scales in UV space will be matched for texturing purposes
# TBD: relative / absolute

	objs = cmds.ls(sl=True)

	bbox = cmds.exactWorldBoundingBox(objs)

	scales = {}
	for obj in objs:
		if cmds.nodeType(cmds.listRelatives(obj, s=True, ni=True, f=True)) == "mesh":
			b = cmds.polyEvaluate(obj, b=True)
			b2 = cmds.polyEvaluate(obj, b2=True)
			if b[2][0] > 1e-10 or b[2][1] > 1e-10:
				raise Exception, "objects must be flat in XY plane"
			scales[obj] = (b2[0][1]-b2[0][0])/(b[0][1]-b[0][0])

	for obj in objs:
		if cmds.nodeType(cmds.listRelatives(obj, s=True, ni=True, f=True)) == "mesh":
			cmds.select(cmds.ls(cmds.polyListComponentConversion(obj, tuv=True), fl=True), r=True)
			s = min(scales.values())/scales[obj]
			cmds.polyEditUV(pu=0.5, pv=0.5, su=s, sv=s)
			cmds.polyEditUV(r=False, u=1, v=1)
				
	cmds.select(objs, r=True)


def __updateNClothAttribute(vertices, attribute, value):
# usage: select one cloth polygon object

	pattern = cmds.ls(sl=True)
	if pattern:
		ncloth = jc.helper.findTypeInHistory( pattern[0], "nCloth", True, True )
		if ncloth:
			attrDict = __nClothAttributes()
			if attribute in attrDict:
				perVertAttr = attrDict[attribute][0]
				mapType = attrDict[attribute][1]

				if cmds.attributeQuery(perVertAttr, node=ncloth, ex=True):
					cmds.setAttr(ncloth+"."+mapType, 1)
					vals = cmds.getAttr(ncloth+"."+perVertAttr)
					if not vals:
						raise Exception, "fails to get "+perVertAttr+" for "+ncloth

					indexReg = re.compile("\[([0-9]+)\]")
					for v in vertices:
						m = indexReg.search(v)
						if m:
							i = int(m.group(1))
							if i < len(vals):
								vals[i] = value

					c = "setAttr \"" + ncloth + "."+perVertAttr+"\" -type \"doubleArray\" " + str(len(vals))
					for v in vals:
						c += " " + str(v)
					c += ";"
					mel.eval(c)


def updateNClothAttribute(attribute, defaultValue=0, borderValue=1):
# obsolete
# usage: select cloth polygon objects
# purpose: 
#	The selected object is expected to have skin binded, joints are located along the border.
#	Input Mesh Attract for the border vertices should be set to 1 and the others to 0.
#	As a result, the border of the object will be deformed by the skeleton
#	while rest of it will be deformed by the nCloth solver.

	for s in cmds.ls(sl=True):

		s = cmds.listRelatives(s, s=True, ni=True, pa=True, f=True)
		if not s or len(s) != 1:
			raise Exception, "no shape node is present"
	
		obj = s[0]
		borderVtx = cmds.polyListComponentConversion(__selectBorderEdges(obj), fe=True, tv=True)
		if borderVtx:
			borderVtx = cmds.ls(borderVtx, fl=True)
		else:
			raise Exception, "fail to get border vertices"
	
		cmds.select(obj, r=True)
		__updateNClothAttribute(cmds.ls(cmds.polyListComponentConversion(obj, tv=True), fl=True), attribute, defaultValue)
		__updateNClothAttribute(borderVtx, attribute, borderValue)
	

def __nClothAttributes():
	return	{	"inputMeshAttract": ( "inputAttractPerVertex", "inputAttractMapType" ),
				"thickness": ( "thicknessPerVertex", "thicknessMapType" ),
				"bounce": ( "bouncePerVertex", "bounceMapType" ),
				"friction": ( "frictionPerVertex", "frictionMapType" ),
				"stickiness": ("stickinessPerVertex", "stickinessMapType" ),
				"pointMass": ( "massPerVertex", "massMapType" ),
				"stretchResistance": ( "stretchPerVertex", "stretchMapType" ),
				"bendResistance": ( "bendPerVertex", "bendMapType" ),
				"wrinkle": ( "wrinklePerVertex", "wrinkleMapType" ),
				"rigidity": ( "rigidityPerVertex", "rigidityMapType" ),
				"deformResistance": ( "deformPerVertex", "deformMapType" )
			}


def nClothAttributes():
# obsolete
	return list(__nClothAttributes().keys())


def setKeyframes(*args, **keywords):
# usage: select garment (nCloth)
# clear all keyframes of all stitch joints, nCloth objects and constraints, then set them all over again

	if set(keywords.keys()) != set(['setKeyframesFor', 'stitchStartTime', 'stitchEndTime', 'turnOnConstraintsTime', 'turnOffInputMeshAttractTime']):
		raise Exception, "argument error"
	setKeyframesFor				= keywords['setKeyframesFor']
	stitchStartTime				= keywords['stitchStartTime']
	stitchEndTime				= keywords['stitchEndTime']
	turnOnConstraintsTime		= keywords['turnOnConstraintsTime']
	turnOffInputMeshAttractTime	= keywords['turnOffInputMeshAttractTime']

	for f in setKeyframesFor:
		if f and f not in setKeyframesOptions():
			raise Exception, "parameter invalid: setKeyframesFor"
	
	if args:
		cmds.select(args, r=True)

	for g in cmds.ls(sl=True):
		ncloth = cmds.ls(cmds.listHistory(g), typ="nCloth", fl=True)
		isd = 1
		plug2isd = None
		if ncloth:
			plug2isd = cmds.listConnections(ncloth[0]+".isd", p=True, s=True, d=False)
			if plug2isd:
				cmds.disconnectAttr(plug2isd[0], ncloth[0]+".isd")
			isd = cmds.getAttr(ncloth[0]+".isd")
			cmds.setAttr(ncloth[0]+".isd", 0)	# disabling ncloth would make setting keyframes faster

		opt = setKeyframesOptions()
			
		if opt[0] in setKeyframesFor:
			currentTime = cmds.currentTime(q=True)
	
			joints = cmds.ls(cmds.listHistory(g), typ='joint', fl=True)
			if joints:
				for j in joints:
					if cmds.attributeQuery(__destinationJoint, n=j, ex=True):
						destJoint = cmds.listConnections(j+"."+__destinationJoint)
						if destJoint:
							destJoint = destJoint[0]
							#weights = __disableConstraints(j)
		
							# animate the stitch on pattern
							cmds.currentTime(stitchStartTime, u=True)
							cmds.select(j, r=True)
							keyJoints(True)

							twistRoot = 0
							twistRoot = cmds.getAttr(cmds.listConnections(j+"."+__patternCurve)[0]+"."+__twistRootLeft)
							if cmds.xform(j, q=True, ws=True, rp=True)[0] < 0:
								twistRoot = cmds.getAttr(cmds.listConnections(j+"."+__patternCurve)[0]+"."+__twistRootRight)
	
							cmds.select(j, r=True)
							matchJoints(stitchStartTime, stitchEndTime, twistRoot)

							cmds.currentTime(currentTime, u=True)
		
							#__restoreConstraints(j, weights)
		
							# set keyframes for all blend attributes
							for s in cmds.attributeInfo(j, all=True):
								if "blend" in s:
									currentTime = cmds.currentTime(q=True)
									cmds.currentTime(stitchStartTime + (stitchEndTime - stitchStartTime)*0.9, u=False)
									cmds.setAttr(j+"."+s, 1)
									cmds.setKeyframe(j, at=s)
									cmds.currentTime(stitchEndTime, u=False)
									cmds.setAttr(j+"."+s, 0)
									cmds.setKeyframe(j, at=s)
									cmds.currentTime(currentTime, u=True)

		if opt[1] in setKeyframesFor and ncloth:
			constraints = cmds.ls(cmds.listHistory(ncloth, f=True), typ="dynamicConstraint", fl=True)
			if constraints:
				cmds.cutKey(constraints, at="ena", cl=True)
				cmds.setKeyframe(constraints, at='ena', t=turnOnConstraintsTime-1, v=0, itt="flat", ott="flat")
				cmds.setKeyframe(constraints, at='ena', t=turnOnConstraintsTime, v=1, itt="flat", ott="flat")
	
		if opt[2] in setKeyframesFor and ncloth:
			cmds.cutKey(ncloth, at="imat", cl=True)
			cmds.setKeyframe(ncloth, at='imat', t=turnOffInputMeshAttractTime-1, v=2, itt="flat", ott="flat")
			cmds.setKeyframe(ncloth, at='imat', t=turnOffInputMeshAttractTime, v=0, itt="flat", ott="flat")

		if ncloth:
			cmds.setAttr(ncloth[0]+".isd", isd)
			if plug2isd:
				cmds.connectAttr(plug2isd[0], ncloth[0]+".isd")


# def matchJoints(setKeyframes=True, matchBy="IK", twistRoot=0):
# obsolete
#	if matchBy not in matchByOptions():
#		raise Exception, "parameter invalid: matchBy"
#
#	if matchBy == "Orient":
#		matchJointsByOrient(setKeyframes)
#	else:
#		matchJointsByIK(setKeyframes, twistRoot)


# def matchByOptions():
# obsolete
#	return [ "IK", "Orient" ]


def setKeyframesOptions():
	return [ "Stitches", "nConstraints", "nCloth" ]


def	attachAdjacentStitches(*args, **keywords):
# usage: select 2 joint chains
# the last joint in the first selected joint chain will point-constraint the first joint in the second selected joint chain
# the blend point attribute on the target joint will be animated such that it is one 90% of the time and will become zero at stitchEndTime

	if set(keywords.keys()) != set(['stitchStartTime', 'stitchEndTime']):
		raise Exception, "argument error"

	stitchStartTime = keywords['stitchStartTime']
	stitchEndTime = keywords['stitchEndTime']

	if args:
		cmds.select(args, r=True)

	sel = cmds.ls(sl=True, typ="joint", fl=True)
	if not sel or len(sel) < 2:
		raise Exception, "not enough selection"
	if len(sel) > 2:
		raise Exception, "too many selection"
		
	t = sel[0]
	while cmds.listRelatives(t, c=True, typ="joint"):
		t = cmds.listRelatives(t, c=True, typ="joint", f=True)[0]

	o = sel[1]
	while cmds.listRelatives(o, p=True, typ="joint"):
		o = cmds.listRelatives(o, p=True, typ="joint", f=True)[0]

	ncloth = cmds.ls(cmds.listHistory(o, f=True), type='nCloth')
	isd = 1
	plug2isd = None
	if ncloth:
		plug2isd = cmds.listConnections(ncloth[0]+".isd", p=True, s=True, d=False)
		if plug2isd:
			cmds.disconnectAttr(plug2isd[0], ncloth[0]+".isd")
		isd = cmds.getAttr(ncloth[0]+".isd")
		cmds.setAttr(ncloth[0]+".isd", 0)

	tl = cmds.pointConstraint(o, q=True, tl=True)
	if not tl or t not in tl:
		cmds.pointConstraint(t, o, mo=True)

	if not cmds.attributeQuery("blendPoint1", n=o, ex=True):
		mel.eval("warning \"no keyframe has been set on "+o+"\"")
		return
	
	currentTime = cmds.currentTime(q=True)
	cmds.currentTime(stitchStartTime + (stitchEndTime - stitchStartTime)*0.9, u=False)
	cmds.setAttr(o+".blendPoint1", 1)
	cmds.setKeyframe(o, at="blendPoint1")
	cmds.currentTime(stitchEndTime, u=False)
	cmds.setAttr(o+".blendPoint1", 0)
	cmds.setKeyframe(o, at="blendPoint1")
	cmds.currentTime(currentTime, u=True)

	if ncloth:
		cmds.setAttr(ncloth[0]+".isd", isd)
		if plug2isd:
			cmds.connectAttr(plug2isd[0], ncloth[0]+".isd")


def	deleteGarment(*args):

	if args:
		cmds.select(args, r=True)

	cmds.select(cmds.listRelatives(cmds.listRelatives(s=True, type='mesh', f=True), p=True, f=True), r=True)
	for g in cmds.ls(sl=True):
		h = cmds.listHistory(g)
		nc = cmds.ls(h, typ="nCloth", fl=True)
		if nc:
			dc = cmds.ls(cmds.listHistory(nc, f=True), typ="dynamicConstraint", fl=True)
			if dc:
				dc = cmds.listRelatives(dc, p=True)
				cmds.select(dc, r=True)
				mel.eval("removeDynamicConstraint \"selected\"")
			cmds.select(g, r=True)
			mel.eval("removeNCloth \"selected\"")
		sk = cmds.ls(h, typ="skinCluster", fl=True)
		if sk:
			joints = cmds.ls(cmds.listHistory(sk), typ="joint", fl=True)
			cmds.skinCluster(g, e=True, ub=True)
			for j in joints:
				if cmds.objExists(j) and cmds.attributeQuery(__destinationJoint, n=j, ex=True):
					c = cmds.listConnections(j+"."+__destinationJoint)
					if c:
						cmds.delete(c)
					cmds.delete(j)
		follicles = cmds.listConnections(g, type='follicle')
		if follicles:
			# delete buttons only if it's a duplicate
			if cmds.listConnections(g+".message"):
				for f in follicles:
						b = cmds.listRelatives(f, ad=True, type='mesh', f=True)
						if b:
							cmds.parent(cmds.listRelatives(b, p=True, f=True), w=True)
			cmds.delete(follicles)
		cmds.delete(g)


def	duplicateGarment(*args, **keywords):
# usage: select ncloth object(s)
# purpose: duplicate garment at different stages (eg. the end of stitching) of posing

	if args:
		cmds.select(args, r=True)

	meshes = cmds.listRelatives(typ="mesh", f=True, s=True, ni=True)
	if not meshes:
		raise Exception, "no mesh selected"

	constraintSet = set([])
	newNCloth = {}

	for garment in meshes:

		nc = jc.helper.findTypeInHistory(garment, type="nCloth")
		if not nc:
			raise Exception, "selected object is not an ncloth object"

		# selected shape is start shape
		# restShapeMesh of nCloth (if exists) is rest shape
		# otherwise it is found from the duplicated garment (wrong)
		# otherwise it is found from the history of inMesh

		restShape = cmds.listConnections(nc+".restShapeMesh", sh=True)
		if restShape:
			restShape = restShape[0]
			startShape = cmds.duplicate(garment, rc=True)
			intermediateObjs = set(cmds.listRelatives(startShape, f=True)) - set(cmds.listRelatives(startShape, ni=True, s=True, f=True))
			def f(x): return x.find("Orig") > -1
			l = filter(f, list(intermediateObjs))
			if l:
				restShape = l[0]
			cmds.delete(list(intermediateObjs - set(l)))
		else:
			"""
			startShape = cmds.duplicate(garment, ic=True, rr=True, rc=True)
			shapes = cmds.listRelatives(startShape, s=True, f=True)
			for s in shapes:
				if cmds.listConnections(s+".inMesh", s=True, t="nCloth"):
					cmds.disconnectAttr(nc+".outputMesh", s+".inMesh")
				elif not cmds.listConnections(s) and s.find("Orig") > -1:
					restShape = s
				else:
					cmds.delete(s)
			"""
			startShape = cmds.duplicate(garment, rc=True)
			inMesh = cmds.listConnections(nc+".inputMesh", sh=True)
			meshes = cmds.ls(cmds.listHistory(inMesh), type='mesh')
			for mesh in meshes:
				if cmds.ls(cmds.listHistory(mesh), type='mesh') == [ mesh ]:
					restShape = mesh
					break

		cmds.editDisplayLayerMembers('defaultLayer', startShape)
		
		# create ncloth with start shape
	
		cmds.select(startShape, r=True)
		mel.eval("createNCloth 0;")
		solver = mel.eval("getActiveNucleusNode(true, false);")
		ncloth = cmds.ls(sl=True)
		if ncloth:
			ncloth = ncloth[0]

		# assign rest shape to the new ncloth
		cmds.connectAttr(restShape+".worldMesh", ncloth+".restShapeMesh", force=True)

		# copy attributes (copyAttr doesn't work for nCloth)
		for a in [ 
			#"pfc",
			"srl", "thss", "boce", "fron", "stck", "adng", "cofl", "scfl", "msci", "mxit", \
			"pmss", "rlsc", "cold", "scld", "cll", "wsdi", "wsds", "apds", "apvy", "pou", \
			"por", "cop", "tpc", "lsou", "dcr", "dcg", "dcb", "stch", "comr", "bnd", "bnad", \
			"retn", "reae", "shr", "rity", "dety", \
			#"imat",
			"iadm", "wms", "basc", "stlk", "aclk", "sdmp", "scws", "scpu", "stpc", "pres", \
			"stpe", "incm", "prdg", "pure", "aits", "shol", "igsg", "igsw", "wssh", "lft", \
			"drg", "tdrg" ]:
			if cmds.attributeQuery(a, node=nc, ex=True):
				cmds.setAttr(ncloth+"."+a, cmds.getAttr(nc+"."+a))

		for a in ["inputAttractMap", "thicknessMap", "bounceMap", "frictionMap", \
					"stickinessMap", "massMap", "stretchMap", "bendMap", \
					"wrinkleMap", "rigidityMap", "deformMap"]:
			if cmds.attributeQuery(a, node=nc, ex=True):
				map = cmds.listConnections(nc+"."+a, p=True)
				if map:
					cmds.connectAttr(map[0], ncloth+"."+a, force=True)

		for c in cmds.ls(cmds.listHistory(nc, f=True), typ="dynamicConstraint", l=True):
			# duplicate both weld and point-to-surface constraints
			if cmds.getAttr(c+".constraintMethod") == 0 or cmds.getAttr(c+".constraintMethod") == 1:
				constraintSet |= set([c])

		newNCloth[nc] = ncloth

		# duplicate buttons
		# cases: garment and subgarment

		o = cmds.listConnections(ncloth+'.outputMesh')[0]
		for f in cmds.ls(cmds.listHistory(garment, f=True), type='follicle', l=True):
			t = cmds.duplicate(f, rr=True)[0]
			f = cmds.listRelatives(t, type='follicle', f=True)[0]
			cmds.connectAttr(o+".worldMatrix", f+".inputWorldMatrix")
			cmds.connectAttr(o+'.outMesh', f+'.inputMesh')
			cmds.connectAttr(f+'.outTranslate', t+'.translate')
			cmds.connectAttr(f+'.outRotate', t+'.rotate')
			cmds.editDisplayLayerMembers('defaultLayer', t)

	# duplicate constraints

	for c in list(constraintSet):
		constraint = cmds.duplicate(c)
		cmds.editDisplayLayerMembers('defaultLayer', constraint)
		for i in range(cmds.getAttr(c+".componentIds", s=True)):
			co = cmds.listConnections(c+".componentIds["+str(i)+"]")
			nc = cmds.listConnections(co[0]+".objectId", sh=True)
			component = cmds.duplicate(co)
			cmds.connectAttr(component[0]+".outComponent", constraint[0]+".componentIds["+str(i)+"]")
			if nc[0] in newNCloth:
				cmds.connectAttr(newNCloth[nc[0]]+".nucleusId", component[0]+".objectId")
			else:
				cmds.connectAttr(nc[0]+".nucleusId", component[0]+".objectId")
		j = 0
		while cmds.listConnections(solver+".inputCurrent["+str(j)+"]"):
			j += 1
		cmds.connectAttr(constraint[0]+".evalCurrent[0]", solver+".inputCurrent["+str(j)+"]")
		j = 0
		while cmds.listConnections(solver+".inputStart["+str(j)+"]"):
			j += 1
		cmds.connectAttr(constraint[0]+".evalStart[0]", solver+".inputStart["+str(j)+"]")


def __vertexSequence(vertices, edge):
# 'vertices' is a list of ordered vertices along a continuous edge
# 'edge' contains only one edge in which there are only two vertices
# compare these two vertices with starting and ending vertices of 'vertices'
# if any comparison succeeds, 'edge' would extend the continuous edge
# and the extra vertex would be put in front of or at the back of 'vertices'
	v = cmds.ls(cmds.polyListComponentConversion(edge, tv=True), fl=True)
	if not vertices:
		for i in v:
			vertices.append(i)
	elif vertices[0] == v[0]:
		vertices.insert(0,v[1])
	elif vertices[0] == v[1]:
		vertices.insert(0,v[0])
	elif vertices[-1] == v[0]:
		vertices.append(v[1])
	elif vertices[-1] == v[1]:
		vertices.append(v[0])


def __findContinuousEdge(vertices, edges):
# find one continous edge from 'edges' and put it into 'vertices'
# return the remaining edges outside the continuous edge
	prevEdges = []
	nextEdges = edges
	while set(prevEdges) != set(nextEdges):
		prevEdges = nextEdges
		nextEdges = []
		for e in prevEdges:
			prevVertices = copy.copy(vertices)
			__vertexSequence(vertices, e)
			if prevVertices == vertices:
				nextEdges.append(e)
	return nextEdges


def __findAllContinuousEdges(edges):
	continuousEdges = []
	while edges:
		vertices = []
		edges = __findContinuousEdge(vertices, edges)
		continuousEdges.append(vertices)
	return continuousEdges


def	createButtonConstraint(interval=6, flip=False):
	__createGroupConstraint("pointToPoint", interval, flip)


def	createZipConstraint(flip=False):
	__createGroupConstraint("pointToPoint", 0, flip)


def	createHingeConstraint(flip=False, rotate=False):
	__createGroupConstraint("transform", 0, flip, rotate)


def	__createGroupConstraint(constraintType, interval=0, flip=False, rotate=False):
# usage: select two continuous edges containing equal number of vertices
# purpose: create "pointToPoint" or "transform" contraints along the length of input edges

	edges = cmds.ls(sl=True, fl=True)
	if not edges:
		raise Exception, "no selection"

	for e in edges:
		if e.find(".e") < 0:
			raise Exception, "invalid selection"

	ncloth = jc.helper.findTypeInHistory(cmds.ls(edges, o=True), "nCloth")
	if not ncloth:
		raise Exception, "selection does not belong to any nCloth object"

	edges = __findAllContinuousEdges(edges)
	if len(edges) < 2:
		raise Exception, "not enough continuous edges found"
	if len(edges) > 2:
		raise Exception, "too many continuous edges found"
	if len(edges[0]) != len(edges[1]):
		raise Exception, "edge lengths are not equal"

	# mass execution of "createNConstraint" would make Maya appear hung
	# to avoid it, nucleus is turned off before entering the loop wrapping "createNConstraint"

	nucleus = cmds.listConnections(ncloth+".currentState")
	nucleusOn = 0
	t = cmds.currentTime(q=True)
	if nucleus:
		nucleus = nucleus[0]
		nucleusOn = cmds.getAttr(nucleus+".enable")
		cmds.setAttr(nucleus+".enable", 0)

	constraints = []
	follicles = []
	rge = range(len(edges[0]))
	if interval > 0:
	  rge = range(0, len(edges[0]), interval)
	for i in rge:
		if constraintType == "pointToPoint":
			if flip:
				cmds.select(edges[0][i], edges[1][-1-i], r=True)
			else:
				cmds.select(edges[0][i], edges[1][i], r=True)
			mel.eval("createNConstraint pointToPoint 0")
			c = cmds.ls(sl=True, typ="dynamicConstraint")
			if c:
				constraints += c
		else:
			if flip:
				tuple = __createHingeConstraint(edges[rotate][i], edges[not rotate][-1-i])
			else:
				tuple = __createHingeConstraint(edges[rotate][i], edges[not rotate][i])
			constraints.append(tuple[0])
			follicles.append(tuple[1])

	if nucleus and nucleusOn:
		cmds.setAttr(nucleus+".enable", 1)
		cmds.currentTime(t)

	if follicles:
		for f in follicles:
			c = cmds.listRelatives(f, ad=True, f=True, typ="dynamicConstraint")
			if c:
				constraints += c
	
	if constraints:
		attributes = [ 
			"ena",
			"strength",
			"tangentStrength",
			"glueStrength",
			"glueStrengthScale",
			"bend",
			"bendStrength",
			"bendBreakAngle",
			"motionDrag",
			"dropoffDistance",
			"force",
			"restLengthMethod",
			"restLength",
			"restLengthScale",
			"excludeCollisions",
			"damp",
			"maxIterations",
			"minIterations" ]
	
		master = cmds.duplicate(constraints[0])[0]
		try:
			cmds.parent(master, w=True)
		except RuntimeError:
			pass
		for a in [ "tx", "ty", "tz", "rx", "ry", "rz" ]:
			cmds.setAttr(master+"."+a, 0)
		for a in [ "sx", "sy", "sz" ]:
			cmds.setAttr(master+"."+a, 1)
		for a in [ "tx", "ty", "tz", "rx", "ry", "rz", "sx", "sy", "sz" ]:
			cmds.setAttr(master+"."+a, l=True, k=False, cb=False)

		for s in constraints:
			for a in attributes:
				cmds.connectAttr(master+"."+a, s+"."+a, f=True)
			
		cmds.select(constraints, r=True)
		a = []
		b = constraints
		while a != b:
			b = a
			a = cmds.pickWalk(d="up")
		cmds.parent(cmds.ls(sl=True), master, a=True)


def	__createHingeConstraint(v0, v1):
# usage: v0 = beginning vertex, v1 = ending vertex

	# 	create transform constraint at v0
	cmds.select(v0, r=True)
	mel.eval("createNConstraint transform 0")
	c0 = cmds.ls(sl=True, typ="dynamicConstraint")
	if c0:
		c0 = cmds.listRelatives(c0[0], p=True)[0]

	# 	create transform constraint at v1
	cmds.select(v1, r=True)
	mel.eval("createNConstraint transform 0")
	c1 = cmds.ls(sl=True, typ="dynamicConstraint")
	if c1:
		c1 = cmds.listRelatives(c1[0], p=True)[0]

	#	create joint chain btw vertices
	cmds.select(cl=True)
	j0 = cmds.joint(p=cmds.pointPosition(v0))
	j1 = cmds.joint(p=cmds.pointPosition(v1))
	cmds.joint(j0, e=True, zso=True, oj='xyz', sao='yup')

	#	align root joint's y-axis with vertex normal and point x-axis towards ending vertex
	obj = cmds.ls(v0, o=True)[0]
	cmds.normalConstraint(obj, j0, w=1, aim=[0,1,0], u=[1,0,0], wut="object", wuo=c1)
	cmds.normalConstraint(obj, j0, rm=True)
	cmds.makeIdentity(j0, a=True, r=True)
	
	cmds.parent(c1, j1)

	#	attach root joint to beginning vertex via follicle	
	uv = cmds.ls(cmds.polyListComponentConversion(v0, tuv=True), fl=True)
	if len(uv) > 1:
		raise Exception, "vertex has more than one UVs"
	indexReg = re.compile("\[([0-9]+)\]")
	i = indexReg.search(uv[0])
	if i:
		i = int(i.group(1))
	else:
		raise Exception, "fail to find uv"
	cmds.select(uv, r=True)
	uv = jc.helper.getVertexUV()
	uv = uv[i]
	fol = cmds.createNode("follicle")
	folTform = cmds.listRelatives(fol, p=True)
	cmds.connectAttr(obj + ".outMesh", fol + ".inputMesh")
	cmds.connectAttr(obj + ".worldMatrix[0]", fol + ".inputWorldMatrix")
	#	only translation is connected, rotation is omitted
	cmds.connectAttr(fol + ".outTranslate", folTform[0] + ".translate" )
	cmds.setAttr(fol+".parameterU", uv[0])
	cmds.setAttr(fol+".parameterV", uv[1])
	cmds.parent(j0, folTform[0])

	return (c0, folTform[0])


def	deleteGroupConstraint():
	s = cmds.ls(sl=True)
	if s:
		c = cmds.listRelatives(s, ad=True, f=True, typ="dynamicConstraint")
		if c:
			for a in c:
				pa = cmds.listRelatives(a, p=True)
				if pa:
					cmds.select(pa, r=True)
					mel.eval("removeDynamicConstraint \"selected\";")
		if not cmds.listRelatives(s, ad=True, f=True):
			cmds.delete(s)


class	pattern:
	serial = 0

	def	__init__(self, name=None):
		pattern.serial += 1
		self.locator = 'pattern'+str(pattern.serial)
		self.curves = []					# array of strings (curve names)
		#self.edges = []						# sorted array of curves without that at x=0 (for use with Garment Editor)
		self.mirror = "True"
		self.reverseNormal = "False"
		self.resolution = "1.0"
		self.frameState = False
		if name != None:
			self.locator = name


class	stitch:
	serial = 0

	def	__init__(self, name=None):
		stitch.serial += 1
		self.destination = 'stitch'+str(stitch.serial)
		self.curves = []					# array of strings (curve names)
		self.numberOfJoints = "10"
		self.stretch = "False"
		self.bind = "True"
		self.frameState = False
		if name != None:
			self.destination = name


class	constraint:
	serial = 0

	def	__init__(self, name=None):
		constraint.serial += 1
		self.name = 'constraint'+str(constraint.serial)
		self.attachable = None
		self.curves = []					# array of strings (curve names)
		self.frameState = False
		if name != None:
			self.name = name


class	subgarment:
	serial = 0

	def	__init__(self, name=None):
		subgarment.serial += 1
		self.layout = 'subgarment'+str(subgarment.serial)
		self.prefix = ''
		self.nClothPreset = 'None'
		self.buttons = []
		self.patterns = []				# array of pattern objects
		self.frameState = False
		if name != None:
			self.layout = name

	def	append(self, p):
		if isinstance(p, pattern):
			self.patterns.append(p)


class	garment:
	# patterns and stitches are lists of dictionaries which contain name-value pair of parameters
	# the 'locator' and 'destination' items must be unique in patterns and stitches repsectively
	# paramter type is either string or list of strings
	# paramter type is changed when it's being put in or taken out from the UI controls

	subgarments = []					# array of subgarment objects
	stitches = []							# array of stitch objects
	constraints = []
	globals = {}
	__moduleName = ""

	def	__init__(self, moduleName):
		self.subgarments = []
		self.stitches = []
		self.constraints = []
		self.globals = {	\
			'turnOffUndo':"True",	\
			'attachStitches':"True",	\
			'rebuildDestinationCurve':"False",	\
			'rebuildUV':"True",	\
			'useGlobalResolution':"True",	\
			'resolution':"1.0",	\
			'timeOrigin':"0",	\
			'stitchStartTime':"1",	\
			'stitchEndTime':"40",	\
			'turnOnConstraintsTime':"50",	\
			'turnOffInputMeshAttractTime':"60",	\
			'passiveCollider':"",	\
			'garment':""	}
		self.__moduleName = moduleName
		self.newSubgarment()

	def	newSubgarment(self, name=None):
		if name and self.getSubgarment(name):
			raise Exception, "subgarment already exists"
		item = subgarment(name)
		self.subgarments.append(item)
		return item

	def	newPattern(self, subgarmentLayout, name=None):
		if name and self.getPattern(name):
			raise Exception, "pattern already exists"
		s = self.getSubgarment(subgarmentLayout)
		if not s:
			raise Exception, "subgarment not exists"
		item = pattern(name)
		s.append(item)
		return item

	def	newStitch(self, name=None):
		if name and self.getStitch(name):
			raise Exception, "stitch already exists"
		item = stitch(name)
		self.stitches.append(item)
		return item

	def	newConstraint(self):
		item = constraint()
		self.constraints.append(item)
		return item

	def	getSubgarment(self, name):
		for s in self.subgarments:
			if s.layout == name:
				return s
			for p in s.patterns:
				if p.locator == name:
					return s

	def	getPattern(self, name):
		for s in self.subgarments:
			for p in s.patterns:
				if p.locator == name:
					return p

	def	getStitch(self, name):
		for s in self.stitches:
			if s.destination == name:
				return s

	def	getConstraint(self, name):
		for s in self.constraints:
			if s.name == name:
				return s

	def	removeSubgarment(self, name):
		if len(self.subgarments) > 1:
			for s in self.subgarments:
				if s.layout == name:
					self.subgarments.remove(s)
					return
				for p in s.patterns:
					if p.locator == name:
						self.subgarments.remove(s)
						return

	def	removePattern(self, name):
		for s in self.subgarments:
			for p in s.patterns:
				if p.locator == name:
					s.patterns.remove(p)
					return
	
	def	removeStitch(self, name):
		for s in self.stitches:
			if s.destination == name:
				self.stitches.remove(s)

	def	removeConstraint(self, name):
		for s in self.constraints:
			if s.name == name:
				self.constraints.remove(s)

	def	checkStitchLength(self, name):
		s = self.getStitch(name)
		if s:
			dl = __findCurveLength__(s.destination)
			for c in s.curves:
				if __findCurveLength__(c) < dl and s.stretch == "False":
					mel.eval('warning "'+c+' is shorter than '+s.destination+', Stretch is on for stitch '+name+'"')
					s.stretch = "True"
					return False
		return True

	def	addSubgarment(self, objects):
		objects = [x for x in objects if cmds.objExists(x) and (cmds.listRelatives(x, typ='locator') or cmds.listRelatives(x, typ='nurbsCurve'))]
		if objects and cmds.listRelatives(objects, typ='locator') and cmds.listRelatives(objects, typ='nurbsCurve'):
			s = self.newSubgarment(cmds.listRelatives(cmds.listRelatives(objects, typ='locator'), p=True)[0])
			self.addPattern(s.layout, objects)
		else:
			raise Exception, "no selection or selection invalid"

	def	addPattern(self, subgarmentLayout, objects):
		objects = [x for x in objects if cmds.objExists(x) and (cmds.listRelatives(x, typ='locator') or cmds.listRelatives(x, typ='nurbsCurve'))]
		if objects and cmds.listRelatives(objects, typ='locator') and cmds.listRelatives(objects, typ='nurbsCurve'):
			p = self.newPattern(subgarmentLayout, cmds.listRelatives(cmds.listRelatives(objects, typ='locator'), p=True)[0])
			p.locator = cmds.listRelatives(cmds.listRelatives(objects, typ='locator', f=True), p=True)[0]
			p.curves = cmds.listRelatives(cmds.listRelatives(objects, typ='nurbsCurve', f=True), p=True)
		else:
			raise Exception, "no selection or selection invalid"

	def	addStitch(self, objects):
		objects = [x for x in objects if cmds.objExists(x) and cmds.listRelatives(x, typ='nurbsCurve')]
		if objects and len(objects) > 1:
			s = self.newStitch(objects[0])
			s.destination = objects[0]
			s.curves = objects[1:]
			self.checkStitchLength(s.destination)
		else:
			raise Exception, "no selection or selection invalid"

	def	addConstraint(self, objects):
		objects = [x for x in objects if cmds.objExists(x) and (cmds.listRelatives(x, typ='locator') or cmds.listRelatives(x, ni=True, typ='mesh') or cmds.listRelatives(x, typ='nurbsCurve'))]
		if objects and (cmds.listRelatives(objects, typ='locator') or cmds.listRelatives(objects, ni=True, typ='mesh')) and cmds.listRelatives(objects, typ='nurbsCurve'):
			s = self.newConstraint()
			if cmds.listRelatives(objects, typ='locator', f=True):
				s.attachable = cmds.listRelatives(cmds.listRelatives(objects, typ='locator', f=True), p=True)[0]
			else:
				s.attachable = cmds.listRelatives(cmds.listRelatives(objects, ni=True, typ='mesh', f=True), p=True)[0]
			s.curves = cmds.listRelatives(cmds.listRelatives(objects, typ='nurbsCurve', f=True), p=True)
		else:
			raise Exception, "no selection or selection invalid"


	def	generateScript(self):
		def validName(s): return s.replace('|','').replace(':','')
	
		def	delimited(s): return "["+s+"]"

		def add(x,y): return x+y

		if not self.globals['passiveCollider']:
			raise Exception, "missing passive collider"
		elif not self.subgarments:
			raise Exception, "missing subgarments"
		elif len(reduce(add, [ x.patterns for x in self.subgarments ])) == 0:
			raise Exception, "missing patterns"
		elif not self.stitches:
			raise Exception, "missing stitches"

		script  = "import traceback, sys\nimport maya.cmds as cmds\nimport maya.mel as mel\n\n"
		script += "turnOffUndo = "+self.globals['turnOffUndo']+"\n"
		script += "attachStitches = "+self.globals['attachStitches']+"\n"
		script += "rebuildUV = "+self.globals['rebuildUV']+"\n"
		script += "rebuildDestinationCurve = "+self.globals['rebuildDestinationCurve']+"\n"
		script += "resolution = "+self.globals['resolution']+"\n"
		script += "timeOrigin = "+self.globals['timeOrigin']+"\n"
		script += "stitchStartTime = "+self.globals['stitchStartTime']+"\n"
		script += "stitchEndTime = "+self.globals['stitchEndTime']+"\n"
		script += "turnOnConstraintsTime = "+self.globals['turnOnConstraintsTime']+"\n"
		script += "turnOffInputMeshAttractTime = "+self.globals['turnOffInputMeshAttractTime']+"\n"
		script += "passiveCollider = '"+self.globals['passiveCollider']+"'\n"
		script += "solver = cmds.ls(cmds.listHistory(passiveCollider, f=True), typ='nucleus')\n"
		script += "if not solver:\n"
		script += "\traise Exception, 'Fail to find nucleus node from passive collider: '+passiveCollider\n"
		script += "mel.eval(\"getActiveNucleusNode(true, false);\")\n"
		script += "mel.eval(\"setActiveNucleusNode(\\\"\"+solver[0]+\"\\\");\")\n"


		script += "\n\n"

		script += "undoState = cmds.undoInfo(q=True, state=True)\n"
		script += "if turnOffUndo: cmds.undoInfo(state=False)\n\n"
		script += "autoKeyframeState = cmds.autoKeyframe(q=True, state=True)\n"
		script += "cmds.autoKeyframe(state=False)\n"
		script += "try:\n"
		script += "\tgarments = []\n"
		script += "\tcmds.currentTime(timeOrigin)\n"

		group = ""			# script to group stitches
		pcurves = []		# all pattern curves
		scurves = []		# all stitch curves
		mirrored = []		# all mirrored pattern curves
		keyframe0 = ""	# script to set keyframe for generated stitch groups at time=timeOrigin
		keyframe1 = ""	# script to set keyframe for generated stitch groups at time=stitchStartTime
		attach = ""			# script to attach adjacent stitches

		# validity check

		pcurves = []
		for s in self.subgarments:
			if s.patterns:
				pcurves += reduce(add, [x.curves for x in s.patterns])
		if self.stitches:
			scurves = reduce(add, [x.curves for x in self.stitches])
		extras =  set(scurves) - set(pcurves)
		if extras:
			raise Exception, "some stitch curves are not pattern curves: "+", ".join(list(extras))

		def f(x): return not cmds.objExists(x)
		objs = filter(f, [ self.globals['passiveCollider'] ] + [ p.locator for p in reduce(add, [ s.patterns for s in self.subgarments ]) ] + pcurves + [ s.destination for s in self.stitches ])
		if objs:
			raise Exception, "some objects are not present: "+", ".join(objs)

		if not int(self.globals['timeOrigin']) < int(self.globals['stitchStartTime']) < int(self.globals['stitchEndTime']) < int(self.globals['turnOnConstraintsTime']) < int(self.globals['turnOffInputMeshAttractTime']):
			raise Exception, "invalid time options"


		# loop over subgarments, patterns and stitches

		for sg in self.subgarments:
			for p in sg.patterns:
				if p.mirror == "True":
					mirrored += p.curves

				script += "\t"+validName(p.locator)+" = jc.clothes.createPattern('"+p.locator+"', "
				script += "'"+"', '".join(p.curves)+"', "

				# check to see if there's keyframe at ty for time = stitchStartTime
				keyTY = False
				n = cmds.listConnections(p.locator+'.ty', t='animCurveTL')
				if n:
					size = cmds.getAttr(n[0]+".ktv", s=True)
					if size > 0:
						for t,v in cmds.getAttr(n[0]+".ktv[:"+str(size-1)+"]"):
							if t == float(self.globals['stitchStartTime']):
								keyTY = True

				if not keyTY:
					# write scripts into keyframe0, keyframe1

					bbx1 = cmds.exactWorldBoundingBox(p.curves)

					# find destination curves of current pattern and hence their bounding box
					# which is used to calculate the y and x displacements of the pattern locator
					destinations = []
					for s in self.stitches:
						for c in s.curves:
							if c in p.curves:
								destinations.append(s.destination)
								break
					if not destinations:
						continue
					bbx2 = cmds.exactWorldBoundingBox(destinations)

					# bounding box of the passive collider is used to calculate the horizontal (x, z) displacement of the stitch groups
					bbx3 = cmds.exactWorldBoundingBox(self.globals['passiveCollider'])

					keyframe1 += "\tcmds.move("+str((bbx2[4]+bbx2[1])/2-(bbx1[4]+bbx1[1])/2)+", '"+p.locator+"', r=True, y=True)\n"

					# move locator depending on its placement dedeuced from reverse normal
					if p.reverseNormal == "False":
						keyframe1 += "\tcmds.move("+str(bbx3[5]+abs(bbx3[5]-bbx3[2])/2)+", '"+p.locator+"', a=True, z=True)\n"
					elif p.reverseNormal == "True":
						keyframe1 += "\tcmds.move("+str(bbx3[2]-abs(bbx3[5]-bbx3[2])/2)+", '"+p.locator+"', a=True, z=True)\n"

					if round(bbx1[0],10) > 0:
						keyframe1 += "\tcmds.move("+str((bbx2[3]+bbx2[0])/2-(bbx1[3]+bbx1[0])/2)+", '"+p.locator+"', r=True, x=True)\n"

					keyframe0 += "\tcmds.setKeyframe('"+p.locator+"', at='t')\n"
					keyframe0 += "\tcmds.setKeyframe('"+p.locator+"', at='r')\n"

					keyframe1 += "\tcmds.setKeyframe('"+p.locator+"', at='t')\n"
					keyframe1 += "\tcmds.setKeyframe('"+p.locator+"', at='r')\n"

				side = ""
				if p.mirror == "True" and round(cmds.xform(p.locator, q=True, ws=True, rp=True)[0], 10) > 0:
					side = "[0]"	# left
				def f(x): return x in scurves
				stitchOnlyCurves = filter(f, p.curves)
				if stitchOnlyCurves:
					group  += "\tcmds.parent("+(side+", ").join(map(delimited, stitchOnlyCurves))+side+", '"+p.locator+"')\n"
					if side:
						side = "[1]"	#right
						group += "\tcmds.parent("+(side+", ").join(map(delimited, stitchOnlyCurves))+side+", cmds.listConnections(cmds.listRelatives('"+p.locator+"', s=True, f=True)[0], t='locator')[0])\n"

				script += "mirror="+p.mirror+", "
				if self.globals['useGlobalResolution'] == "True":
					script += "resolution=resolution, "
				else:
					script += "resolution="+p.resolution+", "
				script += "reverseNormal="+p.reverseNormal
				script += ")\n"

				# find all possible attachments
				# find all attachable pairs from p.curves
				attachables = []
				tolerance = 0.01
				dist = cmds.distanceDimension(sp=[0,0,0], ep=[1,1,1])
				sp = cmds.listConnections(dist+".sp")[0]
				ep = cmds.listConnections(dist+".ep")[0]

				def f(x): return x in scurves
				stitchOnlyCurves = filter(f, p.curves)

				for i in range(0,len(stitchOnlyCurves)):
					for j in range(i+1,len(stitchOnlyCurves)):
						# see if stitchOnlyCurves[i] and stitchOnlyCurves[j] are attachable (ie. if their end points are within tolerance)
						ia = cmds.pointOnCurve(stitchOnlyCurves[i], p=True, top=False, pr=cmds.getAttr(stitchOnlyCurves[i]+".min"))
						ib = cmds.pointOnCurve(stitchOnlyCurves[i], p=True, top=False, pr=cmds.getAttr(stitchOnlyCurves[i]+".max"))
						ja = cmds.pointOnCurve(stitchOnlyCurves[j], p=True, top=False, pr=cmds.getAttr(stitchOnlyCurves[j]+".min"))
						jb = cmds.pointOnCurve(stitchOnlyCurves[j], p=True, top=False, pr=cmds.getAttr(stitchOnlyCurves[j]+".max"))
						pair = []

						cmds.move(ib[0], ib[1], ib[2], sp, a=True)
						cmds.move(ja[0], ja[1], ja[2], ep, a=True)
						if cmds.getAttr(dist+".distance") < tolerance:
							pair = [stitchOnlyCurves[i], stitchOnlyCurves[j]]
						else:
							cmds.move(jb[0], jb[1], jb[2], sp, a=True)
							cmds.move(ia[0], ia[1], ia[2], ep, a=True)
							if cmds.getAttr(dist+".distance") < tolerance:
								pair = [stitchOnlyCurves[j], stitchOnlyCurves[i]]

						if pair:
							if p.mirror == "False":
								attachables.append(map(delimited, pair))
							else:
								# temporarily assume both stitches are mirrored
								attachables.append([delimited(pair[0])+"[0]", delimited(pair[1])+"[0]"])
								attachables.append([delimited(pair[0])+"[1]", delimited(pair[1])+"[1]"])

				cmds.delete(cmds.listRelatives(dist, p=True, f=True))
				cmds.delete(sp)
				cmds.delete(ep)

				# generate attach statements with pairs of curves
				for pair in attachables:
					attach += "\t\tjc.clothes.attachAdjacentStitches("+pair[0]+", "+pair[1]+", stitchStartTime=stitchStartTime, stitchEndTime=stitchEndTime)\n"

			script += "\tgarment = jc.clothes.createGarment("+', '.join([ validName(x.locator) for x in sg.patterns ])+", prefix='"+sg.prefix+"', nClothPreset='"+sg.nClothPreset+"')\n\n"
			if sg.buttons:
				script += "\tjc.clothes.attachButtons(garment, '"+"', '".join([ validName(x) for x in sg.buttons ])+"', buttonType='"+buttonOptions()[0]+"')\n\n"
			script += "\tgarments.append(garment)\n\n"

		script += "\tif len(garments) > 1 and rebuildUV:\n"
		script += "\t\tcmds.select(garments, r=True)\n"
		script += "\t\tjc.clothes.rebuildUV()\n\n"

		for s in self.stitches:
			script += "\t"+validName(s.destination)+" = jc.clothes.createStitch('"+s.destination+"', "
			script += "'"+"', '".join(s.curves)+"', "
			script += "numberOfJoints="+s.numberOfJoints+", "
			script += "rebuildDestinationCurve="+self.globals['rebuildDestinationCurve']+", "
			script += "stretch="+s.stretch+", "
			script += "bind="+s.bind
			script += ")\n"

			for c in s.curves:
				group = group.replace(delimited(c), validName(s.destination)+"["+str(s.curves.index(c)+1)+"]")
				if not not (set(s.curves) - set(mirrored)):
					attach = attach.replace(delimited(c)+"[0]", validName(s.destination)+"["+str(s.curves.index(c)+1)+"]")
					attach = attach.replace(delimited(c)+"[1]", validName(s.destination)+"["+str(s.curves.index(c)+1)+"]")
				attach = attach.replace(delimited(c), validName(s.destination)+"["+str(s.curves.index(c)+1)+"]")

		script += "\n"


		# create weld constraint for within each subgarment and among two subgarments
		sgcurves = []
		for i in range(len(self.subgarments)):
			curves = []
			for s in self.stitches:
				# handle special case for one parttern curve and destination curve is at x=0 (eg. crotch of pants)
				bbox = cmds.exactWorldBoundingBox(s.destination)
				if len(s.curves) > 1 or (round(bbox[0],10) == 0 and round(bbox[3],10) == 0):
					if set(s.curves) == set(s.curves) & set(reduce(add, [ p.curves for p in self.subgarments[i].patterns ])):
						curves += s.curves
			if len(curves) > 0:
				script += "\tjc.clothes.createWeldConstraint('"+"', '".join(curves)+"')\n\n"
			sgcurves.append(curves)
		for i in range(len(self.subgarments)):
			for j in range(i+1, len(self.subgarments)):
				curves = []
				inclusion = set(reduce(add, [ p.curves for p in self.subgarments[i].patterns ]+[ p.curves for p in self.subgarments[j].patterns ])) - set(sgcurves[i]) - set(sgcurves[j])
				for s in self.stitches:
					if len(s.curves) > 1:
						if set(s.curves) == set(s.curves) & inclusion:
							curves += s.curves
				if len(curves) > 0:
					script += "\tjc.clothes.createWeldConstraint('"+"', '".join(curves)+"')\n\n"


		# create point-to-surface constraint for subgarment (eg. pockets)
		script += "\tdef findMesh(attachable):\n"
		script += "\t\tif cmds.ls(cmds.listHistory(attachable, f=True), typ='nRigid'):\n"
		script += "\t\t\treturn attachable\n"
		script += "\t\tcurves = cmds.ls(cmds.listHistory(attachable, f=True), typ='nurbsCurve')\n"
		script += "\t\tif curves:\n"
		script += "\t\t\tmesh = cmds.ls(cmds.listHistory(curves), typ='transform')\n"
		script += "\t\t\tif mesh:\n"
		script += "\t\t\t\tmesh = list(set(mesh))\n"
		script += "\t\t\t\tncloth = cmds.ls(cmds.listHistory(mesh), typ='nCloth')\n"
		script += "\t\t\t\tif ncloth:\n"
		script += "\t\t\t\t\treturn mesh[0]\n\n"
		for w in self.constraints:
			script += "\tmesh = findMesh('"+w.attachable+"')\n"
			script += "\tif mesh:\n"
			script += "\t\tjc.clothes.createWeldConstraint(mesh, '"+"', '".join(w.curves)+"')\n\n"


		if group:
			script += "\tcmds.currentTime(timeOrigin)\n"
			script += group+"\n"
			script += keyframe0
			script += "\tcmds.currentTime(stitchStartTime)\n"
			script += keyframe1
			script += "\tcmds.select(garments, r=True)\n"
			script += "\tjc.clothes.setKeyframes(setKeyframesFor=[\"Stitches\", \"nConstraints\", \"nCloth\"], "
			script += "stitchStartTime=stitchStartTime"
			script += ", stitchEndTime=stitchEndTime"
			script += ", turnOnConstraintsTime=turnOnConstraintsTime"
			script += ", turnOffInputMeshAttractTime=turnOffInputMeshAttractTime"
			script += ")\n\n"

		if attach:
			script += "\tif attachStitches:\n"
			for line in attach.split("\n"):
				# remove those on the right for unmirrored stitches
				if not re.compile("[^\]]\[\d+\][^\[].*\[\d+\]\[1\]").search(line) and not re.compile("\[\d+\]\[1\].*[^\]]\[\d+\][^\[]").search(line):
					script += line+"\n"

		#script += "except:\n\ttraceback.print_exc(limit=2, file=sys.stderr)\n"
		script += "finally:\n\tif turnOffUndo: cmds.undoInfo(state=undoState)\n"
		script += "\tcmds.autoKeyframe(state=autoKeyframeState)\n"
		script += "\tsolver = mel.eval('getActiveNucleusNode(true, false);')\n"
		script += "\tif cmds.objExists(solver) and cmds.getAttr(solver+'.startFrame') > stitchStartTime:\n"
		script += "\t\tcmds.setAttr(solver+'.startFrame', stitchStartTime)\n"

		return script


	def	parseCSV(self, fileObj):
		bool = re.compile("y|true|1", re.I)
		reader = csv.reader(fileObj)
		self.subgarments = []
		patterns = []
		try:
			for row in reader:
				if row[0].lower().startswith("#pattern") and len(row) == 6 and row[1]:
					p = pattern(row[1])
					if row[2]: p.curves = re.split("\s*", row[2].strip())
					if row[3]: p.resolution = row[3]
					if row[4]: p.mirror = str(bool.search(row[4]) != None)
					if row[5]: p.reverseNormal = str(bool.search(row[5]) != None)
					patterns.append(p)
				elif row[0].lower().startswith("#subgarment") and len(row) == 5:
					s = self.newSubgarment()
					if row[1]: s.prefix = row[1]
					if row[2]: s.nClothPreset = row[2]
					if row[3]: s.buttons = re.split("\s*", row[3].strip())
					if row[4]: s.patterns = re.split("\s*", row[4].strip())
				elif row[0].lower().startswith("#stitch") and len(row) == 5 and row[1]:
					s = self.newStitch(row[1])
					if row[2]: s.curves = re.split("\s*", row[2].strip())
					if row[3]: s.numberOfJoints = row[3]
					if row[4]: s.stretch = str(bool.search(row[4]) != None)
				elif row[0].lower().startswith("#constraint") and len(row) == 3:
					s = self.newConstraint()
					if row[1]: s.attachable = row[1]
					if row[2]: s.curves = re.split("\s*", row[2].strip())
				elif row[0].lower().startswith("#global") and len(row) == 13:
					if row[1]: self.globals['turnOffUndo'] = str(bool.search(row[1]) != None)
					if row[2]: self.globals['attachStitches'] = str(bool.search(row[2]) != None)
					if row[3]: self.globals['rebuildUV'] = str(bool.search(row[3]) != None)
					if row[4]: self.globals['rebuildDestinationCurve'] = str(bool.search(row[4]) != None)
					if row[5]: self.globals['useGlobalResolution'] = str(bool.search(row[5]) != None)
					if row[6]: self.globals['resolution'] = row[6]
					if row[7]: self.globals['passiveCollider'] = row[7]
					if row[8]: self.globals['timeOrigin'] = row[8]
					if row[9]: self.globals['stitchStartTime'] = row[9]
					if row[10]: self.globals['stitchEndTime'] = row[10]
					if row[11]: self.globals['turnOnConstraintsTime'] = row[11]
					if row[12]: self.globals['turnOffInputMeshAttractTime'] = row[12]
		except csv.Error, e:
		    raise Exception, 'line %d: %s' % (reader.line_num, e)

		if len(self.subgarments) == 0:
			s = self.newSubgarment()
			s.patterns = patterns
		else:
			for s in self.subgarments:
				def findPatterns(x): return x.locator in s.patterns
				s.patterns = filter(findPatterns, patterns)


	def	generateCSV(self, fileObj):
		def concatenate(x,y): return x+" "+y
		writer = csv.writer(fileObj)
		for s in self.subgarments:
			locators = ""
			for p in s.patterns:
				locators += p.locator+" "
				row = [ "#Pattern", p.locator, reduce(concatenate, p.curves),	p.resolution,	p.mirror, p.reverseNormal ]
				writer.writerow(row)
			if s.buttons:
				row = [ "#Subgarment", s.prefix, s.nClothPreset, reduce(concatenate, s.buttons), locators ]
			else:
				row = [ "#Subgarment", s.prefix, s.nClothPreset, "", locators ]
			writer.writerow(row)
		for s in self.stitches:
			row = [ "#Stitch", s.destination, reduce(concatenate, s.curves), s.numberOfJoints, s.stretch	]
			writer.writerow(row)
		for s in self.constraints:
			row = [ "#Constraint", s.attachable, reduce(concatenate, s.curves)	]
			writer.writerow(row)
		row = [ "#Globals", self.globals['turnOffUndo'], self.globals['attachStitches'],	\
			self.globals['rebuildUV'], self.globals['rebuildDestinationCurve'], \
			self.globals['useGlobalResolution'], self.globals['resolution'], self.globals['passiveCollider'],	\
			self.globals['timeOrigin'], self.globals['stitchStartTime'], self.globals['stitchEndTime'],	\
			self.globals['turnOnConstraintsTime'], self.globals['turnOffInputMeshAttractTime'] ]
		writer.writerow(row)


	def	exportGarment(self, fileObj):
	# IMPORTANT ASSUMPTION: the direction of the mid-curve is always downwards

		def edge(x): return x[0]

		def findPat(c):
			for s in self.subgarments:
				for p in s.patterns:
					if c in p.curves:
						return p

		for s in self.subgarments:
			for p in s.patterns:
				cmds.select(p.curves, r=True)
				corners = getPatternVertices()
				fileObj.write("l %s\n" % p.locator)
				fileObj.write("s %s\n" % p.mirror)
				fileObj.write("n %s\n" % p.reverseNormal)
				# TODO: extract and translate initial positions
				if "front" in p.locator:
					fileObj.write("i 36 0.0 -0.5 0.0 90 0 0 0\n")
				elif "back" in p.locator:
					fileObj.write("i 97 0.0 0.5 0.1 90 0 0 0\n")
				else:
					fileObj.write("i 155 0.6 0.1 0.6 0 65 -5 8\n")
				for c, v in corners:
					r = ''
					if __dist__(v, cmds.pointOnCurve(c, pr=cmds.getAttr(c+'.min'), p=True)) > 1.0e-10:
						r = 'r'
					fileObj.write("v%s %f %f\n" % (r, v[0], v[1]))
					if cmds.getAttr(c+'.degree') == 3:
						for pt in getEdgePoints(c, v):
							fileObj.write("p %f %f\n" % (pt[0], pt[1]))
				fileObj.write("\n")
				if p.mirror == "True" and math.fabs(corners[0][1][0]) < 1.0e-10 and math.fabs(corners[1][1][0]) < 1.0e-10:
					p.edges = map(edge, corners[2:])
				else:
					p.edges = map(edge, corners)

		for s in self.stitches:
			if len(s.curves) == 2:
				a = findPat(s.curves[0])
				b = findPat(s.curves[1])
				fileObj.write("stitch %s %s %d %s %d\n" % (s.destination, a.locator, a.edges.index(cmds.ls(s.curves[0], l=True)[0]), b.locator, b.edges.index(cmds.ls(s.curves[1], l=True)[0])))
				v = cmds.pointOnCurve(s.destination, pr=cmds.getAttr(s.destination+'.min'), p=True)
				fileObj.write("v %f %f %f\n" % (v[0], v[1], v[2]))
				if cmds.getAttr(s.destination+'.degree') == 3:
					for pt in getEdgePoints(s.destination, v):
						fileObj.write("p %f %f %f\n" % (pt[0], pt[1], pt[2]))
				v = cmds.pointOnCurve(s.destination, pr=cmds.getAttr(s.destination+'.max'), p=True)
				fileObj.write("v %f %f %f\n" % (v[0], v[1], v[2]))
				fileObj.write("\n")


	def	importGarment(self, fileObj):
		#TBD: define multiple subgarments

		def createCurveWithEditPoints(points):
			edp2 = om.MPointArray()
			for a in points:
				b = om.MPoint(a[0], a[1], a[2])
				edp2.append(b)
			curveFn = om.MFnNurbsCurve()
			node = om.MFnDependencyNode(curveFn.createWithEditPoints(edp2, 3, om.MFnNurbsCurve.kOpen, False, True, True))
			return node.name()

		def finalPattern():
			if pt0 != None and pt != None:
				if len(edp) == 0:
					if r:
						c = cmds.curve(p=[pt,pt0], k=[0,1], d=1)
					else:
						c = cmds.curve(p=[pt0,pt], k=[0,1], d=1)
				else:
					if r:
						edp.reverse()
						c = createCurveWithEditPoints([pt0]+edp+[pt])
					else:
						c = createCurveWithEditPoints([pt]+edp+[pt0])
				if prefix:
					c = cmds.rename(c, prefix+'C_1')
				patterns[-1].curves.append(c)
	
			s = self.newSubgarment()
			s.patterns = patterns

		loc = re.compile("[l|L]\s+(\w+)")
		sym = re.compile("[s|S]\s+([t|T]rue|[f|F]alse)")
		nor = re.compile("[n|N]\s+([t|T]rue|[f|F]alse)")
		ini = re.compile("[i|I]\s+(-?[0-9]+(\.[0-9]+)?)\s+(-?[0-9]+(\.[0-9]+)?)\s+(-?[0-9]+(\.[0-9]+)?)\s+(-?[0-9]+(\.[0-9]+)?)\s+(-?[0-9]+(\.[0-9]+)?)\s+(-?[0-9]+(\.[0-9]+)?)\s+(-?[0-9]+(\.[0-9]+)?)\s+(-?[0-9]+(\.[0-9]+)?)")
		ver = re.compile("[v|V]([r|R])?\s+(-?[0-9]+(\.[0-9]+)?)\s+(-?[0-9]+(\.[0-9]+)?)")
		poi = re.compile("[p|P]\s+(-?[0-9]+(\.[0-9]+)?)\s+(-?[0-9]+(\.[0-9]+)?)")

		sti = re.compile("stitch\s+(\w+)\s+(\w+)\s+([0-9]+)\s+(\w+)\s+([0-9]+)")
		ver2 = re.compile("[v|V]\s+(-?[0-9]+(\.[0-9]+)?)\s+(-?[0-9]+(\.[0-9]+)?)\s+(-?[0-9]+(\.[0-9]+)?)")
		poi2 = re.compile("[p|P]\s+(-?[0-9]+(\.[0-9]+)?)\s+(-?[0-9]+(\.[0-9]+)?)\s+(-?[0-9]+(\.[0-9]+)?)")

		nam = re.compile("(.*)Loc(Lf)?_[0-9]+")

		self.subgarments = []
		self.stitches = []
		patterns = []

		pt0 = None
		pt = None
		prefix = None
		
		s_pt0 = None

		for line in fileObj:

			m = loc.match(line)
			if m:
				p = m.group(1)
				if p:
					index = -1
					r = None
					prevPrefix = prefix
					prefix = None
					m = nam.match(p)
					if m:
						prefix = m.group(1)
					else:
						prefix = p
					patterns.append(pattern(p))
					cmds.spaceLocator(n=p)
				continue

			m = sym.match(line)
			if m:
				patterns[-1].mirror = m.group(1).capitalize()
				continue

			m = nor.match(line)
			if m:
				patterns[-1].reverseNormal = m.group(1).capitalize()
				continue

			m = ini.match(line)
			if m:
				cmds.move(float(m.group(3)), float(m.group(1)), 0, patterns[-1].locator, a=True)
				continue

			m = ver2.match(line)
			if m:
				x = float(m.group(1))
				y = float(m.group(3))
				z = float(m.group(5))
				s_pt = (x,y,z)
				if not s_pt0:
					s_pt0 = s_pt
				else:
					if len(s_edp) == 0:
						c = cmds.curve(p=[s_pt0,s_pt], k=[0,1], d=1)
					else:
						c = createCurveWithEditPoints([s_pt0]+s_edp+[s_pt])
					c = cmds.rename(c, self.stitches[-1].destination)
					s_pt0 = None
				s_edp = []
				continue
			
			m = poi2.match(line)
			if m:
				x = float(m.group(1))
				y = float(m.group(3))
				z = float(m.group(5))
				s_edp.append((x,y,z))
				continue

			m = ver.match(line)
			if m:
				index += 1
				x = float(m.group(2))
				y = float(m.group(4))
				if index > 0:
					if len(edp) == 0:
						if r:
							c = cmds.curve(p=[(x,y,0),pt], k=[0,1], d=1)
						else:
							c = cmds.curve(p=[pt,(x,y,0)], k=[0,1], d=1)
					else:
						if r:
							edp.reverse()
							c = createCurveWithEditPoints([(x,y,0)]+edp+[pt])
						else:
							c = createCurveWithEditPoints([pt]+edp+[(x,y,0)])
					if prefix:
						c = cmds.rename(c, prefix+'C_1')
					patterns[-1].curves.append(c)
				else:
					if pt0 != None and pt != None:
						if len(edp) == 0:
							if r:
								c = cmds.curve(p=[pt,pt0], k=[0,1], d=1)
							else:
								c = cmds.curve(p=[pt0,pt], k=[0,1], d=1)
						else:
							if r:
								edp.reverse()
								c = createCurveWithEditPoints([pt0]+edp+[pt])
							else:
								c = createCurveWithEditPoints([pt]+edp+[pt0])
						if prevPrefix:
							c = cmds.rename(c, prevPrefix+'C_1')
						patterns[-2].curves.append(c)
					pt0 = (x,y,0)
				r = m.group(1)
				pt = (x,y,0)
				edp = []
				continue

			m = poi.match(line)
			if m:
				x = float(m.group(1))
				y = float(m.group(3))
				edp.append((x,y,0))
				continue

			m = sti.match(line)
			if m:
				if len(self.subgarments) == 0:
					finalPattern()
				self.stitches.append(stitch(m.group(1)))
				pattern1 = self.getPattern(m.group(2))
				box1 = cmds.exactWorldBoundingBox(pattern1.curves[0])
				if box1[0] == 0.0 and box1[3] == 0.0:
					curve1 = int(m.group(3))+2
				else:
					curve1 = int(m.group(3))
				pattern2 = self.getPattern(m.group(4))
				box2 = cmds.exactWorldBoundingBox(pattern2.curves[0])
				if box2[0] == 0.0 and box2[3] == 0.0:
					curve2 = int(m.group(5))+2
				else:
					curve2 = int(m.group(5))
				self.stitches[-1].curves.append(pattern1.curves[curve1])
				self.stitches[-1].curves.append(pattern2.curves[curve2])
				continue

		if len(self.subgarments) == 0:
			finalPattern()


class	garmentBuilderClass:

	__moduleName = ""
	__window = ""
	__gShelfTopLevel = ""
	__garment = None
	__patternListLayout = ""
	__stitchListLayout = ""
	__constraintListLayout = ""
	__currentName = ""
	__currentTextScrollList = ""


	def	__init__(self, moduleName):
		self.__moduleName = moduleName
		self.__window = self.__moduleName.replace('.','_')+"_garmentBuilderWindow"
		self.__gShelfTopLevel = mel.eval("$tempVar=$gShelfTopLevel")
		self.__garment = None
		self.__patternListLayout = ""
		self.__stitchListLayout = ""
		self.__constraintListLayout = ""
		self.__currentName = ""
		self.__currentTextScrollList = ""


	def	open(self, garmentName=None):
		self.__garment = garment(self.__moduleName)

		for x in self.__garment.globals.keys():
			if cmds.optionVar(ex=self.__moduleName+"."+x):
				self.__garment.globals[x] = str(cmds.optionVar(q=self.__moduleName+"."+x))
			elif cmds.optionVar(ex=self.__moduleName+".garmentBuilder."+x):
				self.__garment.globals[x] = str(cmds.optionVar(q=self.__moduleName+".garmentBuilder."+x))
				if x == 'turnOffUndo' or x == 'attachStitches' or x == 'rebuildDestinationCurve':
					self.__garment.globals[x] = str(cmds.optionVar(q=self.__moduleName+".garmentBuilder."+x)==1)

		if not garmentName or (garmentName and garmentName == garmentOptions()[0]):
			garmentName = ""

		if garmentName:
			if garmentName == "Open File":
				fileName = cmds.fileDialog(m=0)
				if fileName:
					#file = open(fileName, "rb")
					#self.__garment.parseCSV(file)
					file = open(fileName, "r")
					self.__garment.importGarment(file)
					file.close()
			else:
				currentTab = cmds.tabLayout(self.__gShelfTopLevel, q=True, st=True)
				cmds.setParent(currentTab)
				if cmds.shelfLayout(currentTab, q=True, ca=True):
					for b in cmds.shelfLayout(currentTab, q=True, ca=True):
						if cmds.shelfButton(b, q=True, ex=True):
							if garmentName == cmds.shelfButton(b, q=True, l=True):
								class garmentCSV:
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
								self.__garment.parseCSV(garmentCSV(cmds.shelfButton(b, q=True, c=True)))


	def	build(self, garmentName=None):
		if not garmentName or (garmentName and garmentName == garmentOptions()[0]):
			garmentName = ""

		self.open(garmentName)
		exec(self.__garment.generateScript())


	def	showWindow(self, garmentName=None):
		if cmds.window(self.__window, q=True, ex=True):
			cmds.showWindow(self.__window)
			return

		if not garmentName or (garmentName and garmentName == garmentOptions()[0]):
			garmentName = ""

		self.open(garmentName)

		w = cmds.window(self.__window, t="Garment Builder", w=360, h=630, mb=True)

		fl = cmds.formLayout()
		tl = cmds.tabLayout(imw=2, imh=2, cr=True)
		cmds.formLayout(fl, e=True, af=[(tl, "top", 5), (tl, "bottom", 0), (tl, "left", 0), (tl, "right", 0)])

		pm = cmds.popupMenu(p=tl)
		cmds.popupMenu(pm, e=True, pmc=self.__moduleName+".garmentBuilderCallback(method='showPopupMenu', popupMenu='"+pm+"', tabLayout='"+tl+"')")

		for s in self.__garment.subgarments:
			cmds.renameUI(cmds.formLayout(p=tl), s.layout)
			cmds.popupMenu(p=s.layout)		# prevent tabLayout's popupMenu to show when right-clicking on the content area
			cmds.tabLayout(tl, e=True, tl=[s.layout, "Patterns"])
			self.showPatterns(s.layout)

		fl = cmds.formLayout(p=tl)
		cmds.popupMenu(p=fl)		# prevent tabLayout's popupMenu to show when right-clicking on the content area
		cmds.tabLayout(tl, e=True, tl=[fl, "Stitches"])
		self.__stitchListLayout = fl
		self.showStitches()

		fl = cmds.formLayout(p=tl)
		cmds.popupMenu(p=fl)		# prevent tabLayout's popupMenu to show when right-clicking on the content area
		cmds.tabLayout(tl, e=True, tl=[fl, "Constraints"])
		self.__constraintListLayout = fl
		self.showConstraints()

		cl = cmds.columnLayout(p=tl, adj=True, co=["both", 10])
		cmds.tabLayout(tl, e=True, tl=[cl, "Globals"])

		cb1 = cmds.checkBoxGrp("turnOffUndo", l="Turn Off Undo:", ncb=1, v1=self.__garment.globals['turnOffUndo']=="True", cl2=["left","left"], ct2=["left","left"], co2=[0,0], h=25, cw2=[180,20], cc=self.__moduleName+".garmentBuilderCallback(method='updateGlobals', columnLayout='"+cl+"')")
		cb2 = cmds.checkBoxGrp("attachStitches", l="Attach Stitches:", ncb=1, v1=self.__garment.globals['attachStitches']=="True", cl2=["left","left"], ct2=["left","left"], co2=[0,0], h=25, cw2=[180,20], cc=self.__moduleName+".garmentBuilderCallback(method='updateGlobals', columnLayout='"+cl+"')")
		cb3 = cmds.checkBoxGrp("rebuildDestinationCurve", l="Rebuild Destination Curves:", ncb=1, v1=self.__garment.globals['rebuildDestinationCurve']=="True", cl2=["left","left"], ct2=["left","left"], co2=[0,0], h=25, cw2=[180,20], cc=self.__moduleName+".garmentBuilderCallback(method='updateGlobals', columnLayout='"+cl+"')")
		cb4 = cmds.checkBoxGrp("rebuildUV", l="Rebuild UV:", ncb=1, v1=self.__garment.globals['rebuildUV']=="True", cl2=["left","left"], ct2=["left","left"], co2=[0,0], h=25, cw2=[180,20], cc=self.__moduleName+".garmentBuilderCallback(method='updateGlobals', columnLayout='"+cl+"')")
		cb5 = cmds.checkBoxGrp("useGlobalResolution", l="Use Global Resolution:", ncb=1, v1=self.__garment.globals['useGlobalResolution']=="True", cl2=["left","left"], ct2=["left","left"], co2=[0,0], h=25, cw2=[180,20], cc=self.__moduleName+".garmentBuilderCallback(method='updateGlobals', columnLayout='"+cl+"')")

		ffg = cmds.floatFieldGrp("resolution", l="Global Resolution:", v1=float(self.__garment.globals['resolution']), h=25, ad2=2, cw2=[175, 20], cl2=["left","left"], ct2=["left","left"], co2=[0,5], cc=self.__moduleName+".garmentBuilderCallback(method='updateGlobals', columnLayout='"+cl+"')")
		if self.__garment.globals['useGlobalResolution']=="True":
			cmds.floatFieldGrp(ffg, e=True, en=True)
		else:
			cmds.floatFieldGrp(ffg, e=True, en=False)

		fl = cmds.formLayout("passiveCollider", p=cl, h=25, w=200)
		tt2 = cmds.text(l="Passive Collider:", w=120, al="left")
		b2 = cmds.button(l=" >> ", w=55, h=20)
		tsl2 = cmds.textScrollList("passiveCollider", nr=1, a=self.__garment.globals['passiveCollider'], h=40)
		cmds.button(b2, e=True, c=self.__moduleName+".garmentBuilderCallback(method='replacePassiveCollider', textScrollList='"+tsl2+"')")
		cmds.formLayout(fl, e=True, af=[(tt2, "top", 7), (tt2, "left", 0)], an=[(tt2, "bottom"), (tt2, "right")])
		cmds.formLayout(fl, e=True, af=[(b2, "top", 7)], ac=[(b2, "left", 0, tt2)], an=[(b2, "bottom"), (b2, "right")])
		cmds.formLayout(fl, e=True, af=[(tsl2, "top", 7), (tsl2, "right", 5)], ac=[(tsl2, "left", 5, b2)], an=[(tsl2, "bottom")])
		cmds.textScrollList(tsl2, e=True, sc=self.__moduleName+".garmentBuilderCallback(method='select', textScrollList='"+tsl2+"')")
		cmds.setParent(cl)

		tfg0 = cmds.intFieldGrp("timeOrigin", l="Time Origin:", nf=1, v1=int(self.__garment.globals['timeOrigin']), h=25, ad2=2, cw2=[175,20], cl2=["left","left"], ct2=["left","left"], co2=[0,0])
		tfg1 = cmds.intFieldGrp("stitchStartTime", l="Stitch Start Time:", nf=1, v1=int(self.__garment.globals['stitchStartTime']), h=25, ad2=2, cw2=[175,20], cl2=["left","left"], ct2=["left","left"], co2=[0,0])
		tfg2 = cmds.intFieldGrp("stitchEndTime", l="Stitch End Time:", nf=1, v1=int(self.__garment.globals['stitchEndTime']), h=25, ad2=2, cw2=[175,20], cl2=["left","left"], ct2=["left","left"], co2=[0,0])
		tfg3 = cmds.intFieldGrp("turnOnConstraintsTime", l="Turn On Constraints Time:", nf=1, v1=int(self.__garment.globals['turnOnConstraintsTime']), h=25, ad2=2, cw2=[175,20], cl2=["left","left"], ct2=["left","left"], co2=[0,0])
		tfg4 = cmds.intFieldGrp("turnOffInputMeshAttractTime", l="Turn Off Input Mesh Attract Time:", nf=1, v1=int(self.__garment.globals['turnOffInputMeshAttractTime']), h=25, ad2=2, cw2=[175,20], cl2=["left","left"], ct2=["left","left"], co2=[0,0])

		cmds.intFieldGrp(tfg0, e=True, cc=self.__moduleName+".garmentBuilderCallback(method='updateTimes', intFieldGrp='"+tfg0+"')")
		cmds.intFieldGrp(tfg1, e=True, cc=self.__moduleName+".garmentBuilderCallback(method='updateTimes', intFieldGrp='"+tfg1+"')")
		cmds.intFieldGrp(tfg2, e=True, cc=self.__moduleName+".garmentBuilderCallback(method='updateTimes', intFieldGrp='"+tfg2+"')")
		cmds.intFieldGrp(tfg3, e=True, cc=self.__moduleName+".garmentBuilderCallback(method='updateTimes', intFieldGrp='"+tfg3+"')")
		cmds.intFieldGrp(tfg4, e=True, cc=self.__moduleName+".garmentBuilderCallback(method='updateTimes', intFieldGrp='"+tfg4+"')")

		cmds.text(l="", h=25)
		tfg6 = cmds.textFieldGrp("garment", l="Garment:", tx=garmentName, h=25, w=100, cw2=[60,40], cl2=["left","left"], ct2=["left","left"], co2=[0,0])


		rl = cmds.rowLayout(p=cl, h=25, nc=5, cl5=["left","center","center","center","center"], cw5=[60,50,50,100,50])
		cmds.text(l="Action:", w=60, al="left")
		cmds.button(l="Build",          c=self.__moduleName+".garmentBuilderCallback(method='action', action='build')", w=50)
		cmds.button(l="Edit",           c=self.__moduleName+".garmentBuilderCallback(method='action', action='edit', textScrollList='"+tsl2+"')", w=50)
		cmds.button(l="Save and Close", c=self.__moduleName+".garmentBuilderCallback(method='action', action='save and close', columnLayout='"+cl+"', textFieldGrp='"+tfg6+"')", w=100)

		cmds.button(l="Cancel",         c=self.__moduleName+".garmentBuilderCallback(method='action', action='cancel')", w=50)

		jc.menu.destroyMenu(self.__window+"|File")
		m = jc.menu.createMenu(self.__window+"|File", w)
		jc.menu.commandItem(m, self.__moduleName+".garmentBuilderCallback(method='importGarment', columnLayout='"+cl+"', tabLayout='"+tl+"')", "Import")
		jc.menu.commandItem(m, self.__moduleName+".garmentBuilderCallback(method='exportGarment')", "Export")

		jc.menu.destroyMenu(self.__window+"|Edit")
		m = jc.menu.createMenu(self.__window+"|Edit", w)
		jc.menu.commandItem(m, self.__moduleName+".garmentBuilderCallback(method='saveSettings')", "Save Settings")
		jc.menu.commandItem(m, self.__moduleName+".garmentBuilderCallback(method='resetSettings', columnLayout='"+cl+"')", "Reset Settings")

		if cmds.about(os=True).startswith("linux"):
			cmds.tabLayout(tl, e=True, cc=self.__moduleName+".garmentBuilderCallback(method='changeTab', tabLayout='"+tl+"')")

		cmds.showWindow(self.__window)


	def	showPatterns(self, subgarmentLayout):
		cmds.setParent(subgarmentLayout)
		if cmds.formLayout(subgarmentLayout, q=1, ca=1):
			[ cmds.deleteUI(c) for c in cmds.formLayout(subgarmentLayout, q=1, ca=1) ]

		firstColWidth = 60
		tempWidth = 200

		s = self.__garment.getSubgarment(subgarmentLayout)

		tfg1 = cmds.textFieldGrp(p=subgarmentLayout, l='Prefix:', h=25, tx=s.prefix, ad2=2, cw2=[90,50], co2=[5,5], ct2=["left","left"], cl2=["left","left"])
		cmds.textFieldGrp(tfg1, e=True, cc=self.__moduleName+".garmentBuilderCallback(method='changeText', textFieldGrp='"+tfg1+"', subgarment='"+subgarmentLayout+"')")

		fl = cmds.formLayout(p=subgarmentLayout, w=tempWidth)
		tfg2 = cmds.textFieldGrp("nCloth", l='nCloth Preset:', h=25, ed=False, tx=s.nClothPreset, ad2=2, cw2=[90,50], co2=[0,0], ct2=["left","left"], cl2=["left","left"])
		b = cmds.button(l="Presets", h=25, w=50)
		pm = cmds.popupMenu(b=1)
		cmds.popupMenu(pm, e=True, pmc=self.__moduleName+".garmentBuilderCallback(method='changePreset', textFieldGrp='"+tfg2+"', popupMenu='"+pm+"', subgarment='"+subgarmentLayout+"')")
		cmds.formLayout(fl, e=True, af=[(b, "top", 2), (b, "right", 5)], an=[(b, "left"), (b, "bottom")])
		cmds.formLayout(fl, e=True, af=[(tfg2, "top", 2), (tfg2, "left", 5)], an=[(tfg2, "bottom")], ac=[(tfg2, "right", 5, b)])

		fl2 = cmds.formLayout(p=subgarmentLayout, w=tempWidth)
		t1 = cmds.text(l="Buttons:", w=90, al="left")
		tsl1 = cmds.textScrollList(ams=True, nr=5, a=s.buttons, w=170, h=60)
		b1 = cmds.button(l="Replace", h=25, w=50, c=self.__moduleName+".garmentBuilderCallback(method='replaceButtons', textScrollList='"+tsl1+"', subgarment='"+subgarmentLayout+"')")
		cmds.formLayout(fl2, e=True, af=[(t1, "top", 7), (t1, "left", 5)], an=[(t1, "bottom"), (t1, "right")])
		cmds.formLayout(fl2, e=True, af=[(tsl1, "top", 7)], ac=[(tsl1, "left", 5, t1)], an=[(tsl1, "bottom"), (tsl1, "right")])
		cmds.formLayout(fl2, e=True, af=[(b1, "top", 7), (b1, "right", 5)], ac=[(b1, "left", 7, tsl1)], an=[(b1, "bottom")])

		cmds.setParent(subgarmentLayout)
		b = cmds.button(l="Add Pattern", h=30, c=self.__moduleName+".garmentBuilderCallback(method='addPattern', subgarmentLayout='"+subgarmentLayout+"')")
		sl = cmds.scrollLayout(cr=True)
		cmds.formLayout(subgarmentLayout, e=True, af=[(tfg1, "top", 5), (tfg1, "left", 10), (tfg1, "right", 10)], an=[(tfg1, "bottom")])
		cmds.formLayout(subgarmentLayout, e=True, ac=[(fl, "top", 0, tfg1)], af=[(fl, "left", 10), (fl, "right", 10)], an=[(fl, "bottom")])
		cmds.formLayout(subgarmentLayout, e=True, ac=[(fl2, "top", 0, fl)], af=[(fl2, "left", 10), (fl2, "right", 10)], an=[(fl2, "bottom")])
		cmds.formLayout(subgarmentLayout, e=True, ac=[(b, "top", 5, fl2)], af=[(b, "left", 10), (b, "right", 10)], an=[(b, "bottom")])
		cmds.formLayout(subgarmentLayout, e=True, ac=[(sl, "top", 10, b)], af=[(sl, "left", 0), (sl, "right", 0), (sl, "bottom", 0)])

		pl = cmds.columnLayout(adj=True)

		for p in reversed(s.patterns):
			fr = cmds.frameLayout(p=pl, cll=True, l=p.locator, cl=p.frameState)
			cmds.frameLayout(fr, e=True, cc=self.__moduleName+".garmentBuilderCallback(method='collapsePatternFrame', collapse=True, name='"+p.locator+"')")
			cmds.frameLayout(fr, e=True, ec=self.__moduleName+".garmentBuilderCallback(method='collapsePatternFrame', collapse=False, name='"+p.locator+"')")

			fl = cmds.formLayout(p=fr)
			cl = cmds.columnLayout(adj=True)
			cmds.formLayout(fl, e=True, af=[(cl, "top", 0), (cl, "bottom", 0), (cl, "left", 0), (cl, "right", 0)])

			fl = cmds.formLayout(p=cl, h=25, w=tempWidth)
			tt2 = cmds.text(l="Locator:", w=firstColWidth, al="left")
			tsl2 = cmds.textScrollList(nr=1, a=p.locator, w=150, h=20)
			cmds.formLayout(fl, e=True, af=[(tt2, "top", 7), (tt2, "left", 5)], an=[(tt2, "bottom"), (tt2, "right")])
			cmds.formLayout(fl, e=True, af=[(tsl2, "top", 7), (tsl2, "right", 7)], ac=[(tsl2, "left", 5, tt2)], an=[(tsl2, "bottom")])

			fl = cmds.formLayout(p=cl, h=65, w=tempWidth)
			tt3 = cmds.text(l="Curves:", w=firstColWidth, al="left")
			tsl3 = cmds.textScrollList(ams=True, nr=5, a=p.curves, w=150, h=60)
			cmds.formLayout(fl, e=True, af=[(tt3, "top", 7), (tt3, "left", 5)], an=[(tt3, "bottom"), (tt3, "right")])
			cmds.formLayout(fl, e=True, af=[(tsl3, "top", 7), (tsl3, "right", 7)], ac=[(tsl3, "left", 5, tt3)], an=[(tsl3, "bottom")])

			ffg = cmds.floatFieldGrp("resolution", p=cl, l="Resolution:", v1=float(p.resolution), cw2=[firstColWidth, 55], cl2=["left","left"], ct2=["left","left"], co2=[5,5])
			cmds.floatFieldGrp(ffg, e=True, cc=self.__moduleName+".garmentBuilderCallback(method='changeFloat', textScrollList='"+tsl2+"', floatFieldGrp='"+ffg+"')")

			fl = cmds.formLayout(p=cl, w=tempWidth)
			cb6a = cmds.checkBox(l="Mirror", v=p.mirror=="True", w=100)
			cb6b = cmds.checkBox(l="Reverse Normal", v=p.reverseNormal=="True", w=100)
			cmds.formLayout(fl, e=True, af=[(cb6a, "top", 7), (cb6a, "left", firstColWidth+10)], an=[(cb6a, "bottom"), (cb6a, "right")])
			cmds.formLayout(fl, e=True, af=[(cb6b, "top", 7), (cb6b, "right", 5)], ac=[(cb6b, "left", 5, cb6a)], an=[(cb6b, "bottom")])

			fl = cmds.formLayout(p=cl, w=tempWidth)
			b4 = cmds.button(l="Remove", c=self.__moduleName+".garmentBuilderCallback(method='removePattern', textScrollList='"+tsl2+"')")
			cmds.formLayout(fl, e=True, af=[(b4, "left", 5), (b4, "right", 5), (b4, "bottom", 5), (b4, "top", 7)])

			cmds.textScrollList(tsl2, e=True, sc=self.__moduleName+".garmentBuilderCallback(method='select', textScrollList='"+tsl2+"')")
			cmds.textScrollList(tsl3, e=True, sc=self.__moduleName+".garmentBuilderCallback(method='select', textScrollList='"+tsl3+"')")
			cmds.checkBox(cb6a, e=True, cc=self.__moduleName+".garmentBuilderCallback(method='changeBoolPattern', textScrollList='"+tsl2+"', checkBox='"+cb6a+"')")
			cmds.checkBox(cb6b, e=True, cc=self.__moduleName+".garmentBuilderCallback(method='changeBoolPattern', textScrollList='"+tsl2+"', checkBox='"+cb6b+"')")


	def	showStitches(self):
		cmds.setParent(self.__stitchListLayout)
		if cmds.formLayout(self.__stitchListLayout, q=1, ca=1):
			[ cmds.deleteUI(c) for c in cmds.formLayout(self.__stitchListLayout, q=1, ca=1) ]
	
		b = cmds.button(l="Add Stitch", h=30, c=self.__moduleName+".garmentBuilderCallback(method='addStitch')")
		sl = cmds.scrollLayout(p=self.__stitchListLayout, cr=True)
		cmds.formLayout(self.__stitchListLayout, e=True, af=[(b, "top", 10), (b, "left", 10), (b, "right", 10)], an=[(b, "bottom")])
		cmds.formLayout(self.__stitchListLayout, e=True, ac=[(sl, "top", 10, b)], af=[(sl, "left", 0), (sl, "right", 0), (sl, "bottom", 0)])

		pl = cmds.columnLayout(adj=True)
		firstColWidth = 60
		tempWidth = 200

		for s in reversed(self.__garment.stitches):
			fr = cmds.frameLayout(p=pl, cll=True, l=s.destination, cl=s.frameState)
			cmds.frameLayout(fr, e=True, cc=self.__moduleName+".garmentBuilderCallback(method='collapseStitchFrame', collapse=True, name='"+s.destination+"')")
			cmds.frameLayout(fr, e=True, ec=self.__moduleName+".garmentBuilderCallback(method='collapseStitchFrame', collapse=False, name='"+s.destination+"')")

			fl = cmds.formLayout(p=fr)
			cl = cmds.columnLayout(adj=True)
			cmds.formLayout(fl, e=True, af=[(cl, "top", 0), (cl, "bottom", 0), (cl, "left", 0), (cl, "right", 0)])

			fl = cmds.formLayout(p=cl, h=25, w=tempWidth)
			tt2 = cmds.text(l="Destination:", w=firstColWidth, al="left")
			tsl2 = cmds.textScrollList(nr=1, a=s.destination, w=150, h=20)
			cmds.formLayout(fl, e=True, af=[(tt2, "top", 7), (tt2, "left", 5)], an=[(tt2, "bottom"), (tt2, "right")])
			cmds.formLayout(fl, e=True, af=[(tsl2, "top", 7), (tsl2, "right", 7)], ac=[(tsl2, "left", 5, tt2)], an=[(tsl2, "bottom")])

			fl = cmds.formLayout(p=cl, h=45, w=tempWidth)
			tt3 = cmds.text(l="Curves:", w=firstColWidth, al="left")
			tsl3 = cmds.textScrollList(ams=True, nr=5, a=s.curves, w=150, h=40)
			cmds.formLayout(fl, e=True, af=[(tt3, "top", 7), (tt3, "left", 5)], an=[(tt3, "bottom"), (tt3, "right")])
			cmds.formLayout(fl, e=True, af=[(tsl3, "top", 7), (tsl3, "right", 7)], ac=[(tsl3, "left", 5, tt3)], an=[(tsl3, "bottom")])

			ilg4 = cmds.intSliderGrp(p=cl, l="Joints:", v=int(s.numberOfJoints), f=True, min=0, max=100, fmn=0, fmx=1000, cw3=[firstColWidth, 50, tempWidth-firstColWidth-50], co3=[5,5,5], ct3=["left","left","left"], cl3=["left","left","left"])

			fl = cmds.formLayout(p=cl, w=tempWidth)
			cb5b = cmds.checkBox(l="Stretch", v=s.stretch=="True", w=100)
			cmds.formLayout(fl, e=True, af=[(cb5b, "top", 7), (cb5b, "left", firstColWidth+10)], an=[(cb5b, "bottom"), (cb5b, "right")])

			fl = cmds.formLayout(p=cl, w=tempWidth)
			b4 = cmds.button(l="Remove", c=self.__moduleName+".garmentBuilderCallback(method='removeStitch', textScrollList='"+tsl2+"')")
			cmds.formLayout(fl, e=True, af=[(b4, "left", 5), (b4, "right", 5), (b4, "bottom", 5), (b4, "top", 7)])

			cmds.textScrollList(tsl2, e=True, sc=self.__moduleName+".garmentBuilderCallback(method='select', textScrollList='"+tsl2+"')")
			cmds.textScrollList(tsl3, e=True, sc=self.__moduleName+".garmentBuilderCallback(method='select', textScrollList='"+tsl3+"')")
			cmds.intSliderGrp(ilg4, e=True, cc=self.__moduleName+".garmentBuilderCallback(method='changeIntStitch', textScrollList='"+tsl2+"', intSliderGrp='"+ilg4+"')")
			cmds.checkBox(cb5b, e=True, cc=self.__moduleName+".garmentBuilderCallback(method='changeBoolStitch', textScrollList='"+tsl2+"', checkBox='"+cb5b+"')")


	def	showConstraints(self):
		cmds.setParent(self.__constraintListLayout)
		if cmds.formLayout(self.__constraintListLayout, q=1, ca=1):
			[ cmds.deleteUI(c) for c in cmds.formLayout(self.__constraintListLayout, q=1, ca=1) ]
	
		b = cmds.button(l="Add Constraint", h=30, c=self.__moduleName+".garmentBuilderCallback(method='addConstraint')")
		sl = cmds.scrollLayout(p=self.__constraintListLayout, cr=True)
		cmds.formLayout(self.__constraintListLayout, e=True, af=[(b, "top", 10), (b, "left", 10), (b, "right", 10)], an=[(b, "bottom")])
		cmds.formLayout(self.__constraintListLayout, e=True, ac=[(sl, "top", 10, b)], af=[(sl, "left", 0), (sl, "right", 0), (sl, "bottom", 0)])

		pl = cmds.columnLayout(adj=True)
		firstColWidth = 60
		tempWidth = 200

		for s in reversed(self.__garment.constraints):
			fr = cmds.frameLayout(p=pl, cll=True, l=s.name, cl=s.frameState)
			cmds.frameLayout(fr, e=True, cc=self.__moduleName+".garmentBuilderCallback(method='collapseConstraintFrame', collapse=True, name='"+s.name+"')")
			cmds.frameLayout(fr, e=True, ec=self.__moduleName+".garmentBuilderCallback(method='collapseConstraintFrame', collapse=False, name='"+s.name+"')")

			fl = cmds.formLayout(p=fr)
			cl = cmds.columnLayout(adj=True)
			cmds.formLayout(fl, e=True, af=[(cl, "top", 0), (cl, "bottom", 0), (cl, "left", 0), (cl, "right", 0)])

			fl = cmds.formLayout(p=cl, h=25, w=tempWidth)
			tt2 = cmds.text(l="Attachable:", w=firstColWidth, al="left")
			tsl2 = cmds.textScrollList(nr=1, a=s.attachable, w=150, h=20)
			cmds.formLayout(fl, e=True, af=[(tt2, "top", 7), (tt2, "left", 5)], an=[(tt2, "bottom"), (tt2, "right")])
			cmds.formLayout(fl, e=True, af=[(tsl2, "top", 7), (tsl2, "right", 7)], ac=[(tsl2, "left", 5, tt2)], an=[(tsl2, "bottom")])

			fl = cmds.formLayout(p=cl, h=45, w=tempWidth)
			tt3 = cmds.text(l="Curves:", w=firstColWidth, al="left")
			tsl3 = cmds.textScrollList(ams=True, nr=5, a=s.curves, w=150, h=60)
			cmds.formLayout(fl, e=True, af=[(tt3, "top", 7), (tt3, "left", 5)], an=[(tt3, "bottom"), (tt3, "right")])
			cmds.formLayout(fl, e=True, af=[(tsl3, "top", 7), (tsl3, "right", 7)], ac=[(tsl3, "left", 5, tt3)], an=[(tsl3, "bottom")])

			fl = cmds.formLayout(p=cl, w=tempWidth)
			b4 = cmds.button(l="Remove", c=self.__moduleName+".garmentBuilderCallback(method='removeConstraint', name='"+s.name+"')")
			cmds.formLayout(fl, e=True, af=[(b4, "left", 5), (b4, "right", 5), (b4, "bottom", 5), (b4, "top", 7)])

			cmds.textScrollList(tsl2, e=True, sc=self.__moduleName+".garmentBuilderCallback(method='select', textScrollList='"+tsl2+"')")
			cmds.textScrollList(tsl3, e=True, sc=self.__moduleName+".garmentBuilderCallback(method='select', textScrollList='"+tsl3+"')")


	def	showPopupMenu(self, **keywords):
		pm = keywords['popupMenu']
		tl = keywords['tabLayout']
		cmds.popupMenu(pm, e=True, dai=True)
		tab = cmds.tabLayout(tl, q=True, sti=True)-1
		children = cmds.tabLayout(tl, q=True, ca=True)
		labels = cmds.tabLayout(tl, q=True, tl=True)
		if labels[tab] == 'Patterns':
			cmds.menuItem(l='New Patterns', p=pm, c=self.__moduleName+".garmentBuilderCallback(method='newSubgarment', tabLayout='"+tl+"')")
			if labels.count('Patterns') > 1:
				cmds.menuItem(l='Remove Patterns', p=pm, c=self.__moduleName+".garmentBuilderCallback(method='removeSubgarment', tabLayout='"+tl+"')")


	def	newSubgarment(self, **keywords):
		tl = keywords['tabLayout']
		tab = cmds.tabLayout(tl, q=True, sti=True)
		s = self.__garment.newSubgarment()
		cmds.renameUI(cmds.formLayout(p=tl), s.layout)
		cmds.popupMenu(p=s.layout)		# prevent tabLayout's popupMenu to show when right-clicking on the content area
		cmds.tabLayout(tl, e=True, tl=[s.layout, "Patterns"])
		n = cmds.tabLayout(tl, q=True, nch=True)
		cmds.tabLayout(tl, e=True, mt=[n, tab+1])
		self.showPatterns(s.layout)
		cmds.tabLayout(tl, e=True, sti=tab+1)


	def	removeSubgarment(self, **keywords):
		tl = keywords['tabLayout']
		tab = cmds.tabLayout(tl, q=True, sti=True)-1
		labels = cmds.tabLayout(tl, q=True, tl=True)
		if labels[tab] == 'Patterns' and labels.count('Patterns') > 1:
			children = cmds.tabLayout(tl, q=True, ca=True)
			cmds.deleteUI(children[tab], lay=True)
			self.__garment.removeSubgarment(children[tab])


	def	changeTab(self, **keywords):
		tl = keywords['tabLayout']
		tab = cmds.tabLayout(tl, q=True, sti=True)-1
		labels = cmds.tabLayout(tl, q=True, tl=True)
		if labels[tab] == 'Patterns':
			children = cmds.tabLayout(tl, q=True, ca=True)
			self.showPatterns(children[tab])
		elif labels[tab] == 'Stitches':
			self.showStitches()


	def	collapsePatternFrame(self, **keywords):
		item = self.__garment.getPattern(keywords['name'])
		if item:
			item.frameState = keywords['collapse'] == "True"


	def	collapseStitchFrame(self, **keywords):
		item = self.__garment.getStitch(keywords['name'])
		if item:
			item.frameState = keywords['collapse'] == "True"


	def	collapseConstraintFrame(self, **keywords):
		item = self.__garment.getConstraint(keywords['name'])
		if item:
			item.frameState = keywords['collapse'] == "True"


	# obsolete
	def	importCSV(self, **keywords):
		cl = keywords['columnLayout']
		tl = keywords['tabLayout']
		self.__garment = garment(self.__moduleName)
		f = cmds.fileDialog(m=0)
		if f:
			file = open(f, "rb")
			self.__garment.parseCSV(file)
			file.close()
			labels = cmds.tabLayout(tl, q=True, tl=True)
			children = cmds.tabLayout(tl, q=True, ca=True)
			for i in range(len(labels)):
				if labels[i] == "Patterns":
					cmds.deleteUI(children[i], lay=True)
			i = 1
			for s in self.__garment.subgarments:
				cmds.renameUI(cmds.formLayout(p=tl), s.layout)
				cmds.popupMenu(p=s.layout)		# prevent tabLayout's popupMenu to show when right-clicking on the content area
				cmds.tabLayout(tl, e=True, tl=[s.layout, "Patterns"])
				n = cmds.tabLayout(tl, q=True, nch=True)
				cmds.tabLayout(tl, e=True, mt=[n, i])
				self.showPatterns(s.layout)
				cmds.tabLayout(tl, e=True, sti=i)
				i =+ 1
			self.showStitches()
			self.showConstraints()
			self.updateGlobalsUI(cl)


	# obsolete
	def	exportCSV(self):
		f = cmds.fileDialog(m=1)
		if f:
			file = open(f, "wb")
			self.__garment.generateCSV(file)
			file.close()
			return True
		return False


	def	importGarment(self, **keywords):
		cl = keywords['columnLayout']
		tl = keywords['tabLayout']
		self.__garment = garment(self.__moduleName)
		f = cmds.fileDialog(m=0)
		if f:
			file = open(f, "r")
			self.__garment.importGarment(file)
			file.close()
			labels = cmds.tabLayout(tl, q=True, tl=True)
			children = cmds.tabLayout(tl, q=True, ca=True)
			for i in range(len(labels)):
				if labels[i] == "Patterns":
					cmds.deleteUI(children[i], lay=True)
			i = 1
			for s in self.__garment.subgarments:
				cmds.renameUI(cmds.formLayout(p=tl), s.layout)
				cmds.popupMenu(p=s.layout)		# prevent tabLayout's popupMenu to show when right-clicking on the content area
				cmds.tabLayout(tl, e=True, tl=[s.layout, "Patterns"])
				n = cmds.tabLayout(tl, q=True, nch=True)
				cmds.tabLayout(tl, e=True, mt=[n, i])
				self.showPatterns(s.layout)
				cmds.tabLayout(tl, e=True, sti=i)
				i =+ 1
			self.showStitches()
			self.showConstraints()
			self.updateGlobalsUI(cl)


	def exportGarment(self):
		f = cmds.fileDialog(m=1)
		if f:
			file = open(f, "w")
			self.__garment.exportGarment(file)
			file.close()
			return True
		return False


	def	saveSettings(self):
		cmds.optionVar(iv=(self.__moduleName+".garmentBuilder.turnOffUndo", self.__garment.globals['turnOffUndo']=="True"))
		cmds.optionVar(iv=(self.__moduleName+".garmentBuilder.attachStitches", self.__garment.globals['attachStitches']=="True"))
		cmds.optionVar(iv=(self.__moduleName+".garmentBuilder.rebuildDestinationCurve", self.__garment.globals['rebuildDestinationCurve']=="True"))
		cmds.optionVar(iv=(self.__moduleName+".garmentBuilder.useGlobalResolution", self.__garment.globals['useGlobalResolution']=="True"))
		cmds.optionVar(iv=(self.__moduleName+".garmentBuilder.timeOrigin", int(self.__garment.globals['timeOrigin'])))
		cmds.optionVar(iv=(self.__moduleName+".stitchStartTime", int(self.__garment.globals['stitchStartTime'])))
		cmds.optionVar(iv=(self.__moduleName+".stitchEndTime", int(self.__garment.globals['stitchEndTime'])))
		cmds.optionVar(iv=(self.__moduleName+".turnOnConstraintsTime", int(self.__garment.globals['turnOnConstraintsTime'])))
		cmds.optionVar(iv=(self.__moduleName+".turnOffInputMeshAttractTime", int(self.__garment.globals['turnOffInputMeshAttractTime'])))
		cmds.optionVar(fv=(self.__moduleName+".resolution", float(self.__garment.globals['resolution'])))
		cmds.optionVar(sv=(self.__moduleName+".garmentBuilder.garment", self.__garment.globals['garment']))


	def	resetSettings(self, **keywords):
		cl = keywords['columnLayout']
		temp = garment(self.__moduleName)
		self.__garment.globals = temp.globals
		self.saveSettings()
		self.updateGlobalsUI(cl)


	def	updateGlobalsUI(self, cl):
		for c in cmds.columnLayout(cl, q=True, ca=True):
			if c.find('turnOffUndo') > -1:
				cmds.checkBoxGrp(cl+"|"+c, e=True, v1=self.__garment.globals['turnOffUndo']=="True")
			if c.find('attachStitches') > -1:
				cmds.checkBoxGrp(cl+"|"+c, e=True, v1=self.__garment.globals['attachStitches']=="True")
			if c.find('rebuildUV') > -1:
				cmds.checkBoxGrp(cl+"|"+c, e=True, v1=self.__garment.globals['rebuildUV']=="True")
			if c.find('rebuildDestinationCurve') > -1:
				cmds.checkBoxGrp(cl+"|"+c, e=True, v1=self.__garment.globals['rebuildDestinationCurve']=="True")
			if c.find('useGlobalResolution') > -1:
				cmds.checkBoxGrp(cl+"|"+c, e=True, v1=self.__garment.globals['useGlobalResolution']=="True")
			elif c.find('resolution') > -1:
				cmds.floatFieldGrp(cl+"|"+c, e=True, v1=float(self.__garment.globals['resolution']))
				if self.__garment.globals['useGlobalResolution']=="True":
					cmds.floatFieldGrp(cl+"|"+c, e=True, en=True)
				else:
					cmds.floatFieldGrp(cl+"|"+c, e=True, en=False)
			elif c.find('garment') > -1:
				cmds.textFieldGrp(cl+"|"+c, e=True, tx=self.__garment.globals[c])
			elif c.lower().find('time') > -1:
				cmds.intFieldGrp(cl+"|"+c, e=True, v1=int(self.__garment.globals[c]))
			elif c.find('passiveCollider') > -1:
				cmds.textScrollList(cl+"|"+c+"|"+c, e=True, ra=True)
				cmds.textScrollList(cl+"|"+c+"|"+c, e=True, a=self.__garment.globals[c])


	def	updateGlobals(self, **keywords):
		cl = keywords['columnLayout']
		for i in self.__garment.globals.keys():
			if "turnOffUndo" in i:
				self.__garment.globals[i] = str(cmds.checkBoxGrp(cl+"|"+i, q=True, v1=True)==1)
			if "attachStitches" in i:
				self.__garment.globals[i] = str(cmds.checkBoxGrp(cl+"|"+i, q=True, v1=True)==1)
			if "rebuildUV" in i:
				self.__garment.globals[i] = str(cmds.checkBoxGrp(cl+"|"+i, q=True, v1=True)==1)
			if "rebuildDestinationCurve" in i:
				self.__garment.globals[i] = str(cmds.checkBoxGrp(cl+"|"+i, q=True, v1=True)==1)
			if "useGlobalResolution" in i:
				v = cmds.checkBoxGrp(cl+"|"+i, q=True, v1=True)
				self.__garment.globals[i] = str(v==1)
				if v:
					cmds.floatFieldGrp(cl+"|resolution", e=True, en=True)
				else:
					cmds.floatFieldGrp(cl+"|resolution", e=True, en=False)
			elif "resolution" in i:
				value = cmds.floatFieldGrp(cl+"|"+i, q=True, v1=True)
				if value <= 0.0:
					cmds.floatFieldGrp(cl+"|"+i, e=True, v1=float(self.__garment.globals[i]))
					raise Exception, "resolution must be greater than 0"
				self.__garment.globals[i] = str(value)


	def	updateTimes(self, **keywords):
		tfg = keywords['intFieldGrp']
		i = cmds.intFieldGrp(tfg, q=True, v1=True)
		t = tfg.split('|')[-1]
		self.__garment.globals[t] = str(i)


	def	action(self, **keywords):
		action = keywords['action']

		if action == 'build':
			exec(self.__garment.generateScript())
			return

		if action == 'edit':
			body = cmds.textScrollList(keywords['textScrollList'], q=True, ai=True)
			if len(body) == 1:
				self.__garment.globals['passiveCollider'] = body[0]
				tempfd, temppath = tempfile.mkstemp()
				tempf = os.fdopen(tempfd, 'w')
				self.__garment.exportGarment(tempf)
				tempf.close()
				cmds.select(body, r=True)
				if cmds.pluginInfo('jcClothes',q=True,l=True):
					mel.eval("jcGarmentEditor -f \"%s\";\n" % temppath.replace('\\','/'))
					os.remove(temppath)
				else:
					raise Exception, "jcClothes plugin not loaded"
			return

		if action == 'cancel':
			cmds.deleteUI(self.__window)
			return

		cl = keywords['columnLayout']
		tfg = keywords['textFieldGrp']

		name = cmds.textFieldGrp(tfg, q=True, tx=True)
		if not name:
			raise Exception, "missing garment name"
		self.__garment.globals['garment'] = name

		if name == "Open File":
			if self.exportCSV():
				cmds.deleteUI(self.__window)
			return

		class temp:
			buffer = ""
			def	__init__(self):
				self.buffer = ""
			def	write(self, content):
				self.buffer += content
			def writerow(self, content):
				self.buffer += content + "\n"
		tmpfile = temp()

		self.updateGlobals(columnLayout=cl)
		self.__garment.generateCSV(tmpfile)

		self.saveSettings()

		currentTab = cmds.tabLayout(self.__gShelfTopLevel, q=True, st=True)
		cmds.setParent(currentTab)

		tmpfile.buffer += "jc.clothes.buildGarment('"+name+"')"
		if cmds.shelfLayout(currentTab, q=True, ca=True):
			for b in cmds.shelfLayout(currentTab, q=True, ca=True):
				if cmds.shelfButton(b, q=True, ex=True):
					if name == cmds.shelfButton(b, q=True, l=True):
						cmds.shelfButton(b, e=True, c=tmpfile.buffer.strip().replace("\r\n","\r"))
						cmds.deleteUI(self.__window)
						return

		mel.eval("scriptToShelf \""+name+"\" \""+tmpfile.buffer.strip().replace("\r\n","\\r").replace("\"","\\\"")+"\" \"0\"")
		cmds.deleteUI(self.__window)
	
	
	def	replacePassiveCollider(self, **keywords):
		tsl = keywords['textScrollList']
		if cmds.ls(sl=True):
			object = cmds.ls(sl=True)[0]
			solver = cmds.ls(cmds.listHistory(object, f=True), typ='nucleus')
			if solver:
				cmds.textScrollList(tsl, e=True, ra=True)
				cmds.textScrollList(tsl, e=True, a=object)
				self.__garment.globals['passiveCollider'] = object
				return
		raise Exception, "no selection or selection invalid"


	def	addPattern(self, **keywords):
		if 'subgarmentLayout' in keywords:
			layout = keywords['subgarmentLayout']
			self.__garment.addPattern(layout, cmds.ls(sl=True))
			self.showPatterns(layout)


	def	addStitch(self):
		self.__garment.addStitch(cmds.ls(sl=True))
		self.showStitches()


	def	addConstraint(self):
		self.__garment.addConstraint(cmds.ls(sl=True))
		self.showConstraints()


	def	select(self, **keywords):
		def exists(x,y): return x and y
		if 'textScrollList' in keywords:
			tsl = keywords['textScrollList']
			if self.__currentTextScrollList and self.__currentTextScrollList != tsl and cmds.textScrollList(self.__currentTextScrollList, q=True, ex=True):
				cmds.textScrollList(self.__currentTextScrollList, e=True, da=True)
			items = cmds.textScrollList(tsl, q=True, si=True)
			if items and reduce(exists, [ cmds.objExists(x) for x in items ]):
				cmds.select(items, r=True)
			self.__currentTextScrollList = tsl


	def	changeIntStitch(self, **keywords):
		tsl = keywords['textScrollList']
		ilg = keywords['intSliderGrp']
		item = self.__garment.getStitch(cmds.textScrollList(tsl, q=True, ai=True)[0])
		item.numberOfJoints = str(cmds.intSliderGrp(ilg, q=True, v=True))


	def	changeBoolPattern(self, **keywords):
		tsl = keywords['textScrollList']
		cb = keywords['checkBox']
		name = cmds.textScrollList(tsl, q=True, ai=True)[0]
		item = self.__garment.getPattern(name)
		label = cmds.checkBox(cb, q=True, l=True)
		label = label.strip().replace(' ','')
		label = label[0].lower() + label[1:]
		if label == 'mirror':
			item.mirror = str(cmds.checkBox(cb, q=True, v=True) == 1)
		elif label == 'reverseNormal':
			item.reverseNormal = str(cmds.checkBox(cb, q=True, v=True) == 1)


	def	changeBoolStitch(self, **keywords):
		tsl = keywords['textScrollList']
		cb = keywords['checkBox']
		name = cmds.textScrollList(tsl, q=True, ai=True)[0]
		item = self.__garment.getStitch(name)
		item.stretch = str(cmds.checkBox(cb, q=True, v=True) == 1)
		if not self.__garment.checkStitchLength(name):
			cmds.checkBox(cb, e=True, v=item.stretch=="True")


	def	changeFloat(self, **keywords):
		tsl = keywords['textScrollList']
		ffg = keywords['floatFieldGrp']
		value = cmds.floatFieldGrp(ffg, q=True, v1=True)
		name = cmds.textScrollList(tsl, q=True, ai=True)[0]
		item = self.__garment.getPattern(name)
		if value <= 0.0:
			cmds.floatFieldGrp(ffg, e=True, v1=float(item.resolution))
			raise Exception, "resolution must be greater than 0"
		item.resolution = str(value)


	def	removePattern(self, **keywords):
		tsl = keywords['textScrollList']
		locator = cmds.textScrollList(tsl, q=True, ai=True)[0]
		s = self.__garment.getSubgarment(locator)
		self.__garment.removePattern(locator)
		self.showPatterns(s.layout)


	def	removeStitch(self, **keywords):
		tsl = keywords['textScrollList']
		self.__garment.removeStitch(cmds.textScrollList(tsl, q=True, ai=True)[0])
		self.showStitches()


	def	removeConstraint(self, **keywords):
		self.__garment.removeConstraint(keywords['name'])
		self.showConstraints()


	def	changeText(self, **keywords):
		tfg = keywords['textFieldGrp']
		value = cmds.textFieldGrp(tfg, q=True, tx=True)
		i = self.__garment.getSubgarment(keywords['subgarment'])
		if i:
			i.prefix = value


	def	changePreset(self, **keywords):
		tfg = keywords['textFieldGrp']
		if 'popupMenu' in keywords:
			pm = keywords['popupMenu']
			l = getNClothPresetsCallback()
			cmds.popupMenu(pm, e=True, dai=True)
			for i in l:
				m = cmds.menuItem(l=i, p=pm)
				if 'subgarment' in keywords:
					cmds.menuItem(m, e=True, c=self.__moduleName+".garmentBuilderCallback(method='changePreset', textFieldGrp='"+tfg+"', menuItem='"+m+"', subgarment='"+keywords['subgarment']+"')")
				else:
					cmds.menuItem(m, e=True, c=self.__moduleName+".garmentBuilderCallback(method='changePreset', textFieldGrp='"+tfg+"', menuItem='"+m+"')")
		elif 'menuItem' in keywords:
			value = cmds.menuItem(keywords['menuItem'], q=True, l=True)
			cmds.textFieldGrp(tfg, e=True, tx=value)
			i = self.__garment.getSubgarment(keywords['subgarment'])
			if i:
				i.nClothPreset = value


	def	replaceButtons(self, **keywords):
		tsl = keywords['textScrollList']
		cmds.textScrollList(tsl, e=True, ra=True)
		s = self.__garment.getSubgarment(keywords['subgarment'])
		if s and cmds.ls(sl=True):
			s.buttons = []
			buttons = cmds.listRelatives(cmds.ls(sl=True), type='mesh')
			if buttons:
				buttons = cmds.listRelatives(buttons, p=True)
				buttons = list(set(buttons))
				cmds.textScrollList(tsl, e=True, a=buttons)
				s.buttons = buttons
				return


	def	callback(self, **keywords):
		a = "self."+keywords['method']+"("
		for (n,v) in keywords.iteritems():
			if n != 'method':
				a += ", "+n+"='"+str(v)+"'"
		eval(a.replace(', ','',1)+")")


##	end of garmentBuilderClass	##




# global variables
__garmentBuilder = None
__garmentBuilderCallback = None


def	garmentBuilderCallback(*args, **keywords):
	__garmentBuilderCallback(*args, **keywords)


def	garmentBuilder(garment=None):
	# as assignment statements would make variables local implicitly, this global statement is necessary
	global __garmentBuilder, __garmentBuilderCallback

	if not __garmentBuilder:
		__garmentBuilder = garmentBuilderClass(__moduleName)
		__garmentBuilderCallback = __garmentBuilder.callback

	__garmentBuilder.showWindow(garment)


def	buildGarment(garment=None):
	# as assignment statements would make variables local implicitly, this global statement is necessary
	global __garmentBuilder, __garmentBuilderCallback

	if not __garmentBuilder:
		__garmentBuilder = garmentBuilderClass(__moduleName)
		__garmentBuilderCallback = __garmentBuilder.callback

	__garmentBuilder.build(garment)


def	buildGarmentFromFile(fileName=None):
	g = garment(__moduleName)
	if not fileName:
		fileName = cmds.fileDialog(m=0)
	if fileName:
		file = open(fileName, "rb")
		g.parseCSV(file)
		file.close()
		exec(g.generateScript())


def	garmentOptions():
	p = [ "Create New" ]
	#p += [ "Open File" ]
	currentTab = cmds.tabLayout(mel.eval("$tempVar=$gShelfTopLevel"), q=True, st=True)
	if cmds.shelfLayout(currentTab, q=True, ca=True):
		for b in cmds.shelfLayout(currentTab, q=True, ca=True):
			if cmds.shelfButton(b, q=True, ex=True):
				if cmds.shelfButton(b, q=True, c=True).lower().startswith("#pattern"):
					p.append(cmds.shelfButton(b, q=True, l=True))
	return p


def	attachLayer(*args, **keywords):
	meshes = cmds.listRelatives(typ="mesh", f=True, s=True, ni=True)
	if not meshes:
		raise Exception, "no mesh selected"

	if 'layer' not in keywords.keys():
		raise Exception, "argument error"

	layer = keywords['layer']
	if not layer or (layer and layer == layerOptions()[0]):
		layer = cmds.createDisplayLayer()

	if not cmds.objExists(layer):
		layer = cmds.createDisplayLayer(n=layer)

	if args:
		cmds.select(args, r=True)

	for garment in meshes:

		nc = jc.helper.findTypeInHistory(garment, type="nCloth")
		if not nc:
			raise Exception, "selected object is not an ncloth object"

		patternCurves = cmds.listConnections(cmds.listRelatives(garment, p=True, f=True)[0]+".message", p=True)
		if patternCurves:
			curves = set()
			locators = set()
			joints = set()
			for p in patternCurves:
				if __pattern in p:
					c = cmds.listRelatives(p.split('.')[0], p=True, f=True)[0]
					curves.add(c)
					if cmds.attributeQuery(__destinationCurve, n=c, ex=True):
						curves.add(cmds.listConnections(c+"."+__destinationCurve)[0])
					s = cmds.listRelatives(c, s=True, f=True)[0]
					if cmds.attributeQuery(__locator, n=s, ex=True):
						l = cmds.listConnections(s+"."+__locator)[0]
						locators.add(l)
						s = cmds.listRelatives(l, s=True, f=True)[0]
						l = cmds.ls(cmds.listRelatives(cmds.listConnections(s), s=True, f=True), type='locator')
						if l:
							locators.add(cmds.listRelatives(l, p=True, f=True)[0])
					if cmds.listConnections(c+".message", p=True):
						for j in cmds.listConnections(c+".message", p=True):
							if __patternCurve in j:
								j = j.split('.')[0]
								if cmds.attributeQuery(__destinationJoint, n=j, ex=True):
									joints.add(cmds.listConnections(j+"."+__destinationJoint)[0])
			if list(curves|locators|joints):
				cmds.editDisplayLayerMembers(layer, list(curves|locators|joints))

		dc = cmds.ls(cmds.listHistory(nc, f=True), type='dynamicConstraint')
		if dc:
			cmds.editDisplayLayerMembers(layer, cmds.listRelatives(dc, p=True, f=True))
		cmds.editDisplayLayerMembers(layer, cmds.listRelatives(nc, p=True, f=True))
		cmds.editDisplayLayerMembers(layer, cmds.listRelatives(garment, p=True, f=True))
		f = cmds.ls(cmds.listHistory(nc, f=True), type='follicle')
		if f:
			cmds.editDisplayLayerMembers(layer, cmds.listRelatives(f, p=True, f=True))
		try:
			cmds.connectAttr(layer+".v", nc+".isd", f=True)
		except:
			pass


def	layerOptions():
	return [ "Create New" ] + cmds.listConnections("layerManager")[1:]


def	__assembleCmd(action):
	# this is a duplication of proc assembleCmd in performCreateNclothCache.mel
	# the global variables do not exist if the option box have not been invoked
	gCacheCurrentProject = "CurrentProject"
	gNclothCacheAutomaticName = "Automatic"
	try:
		gCacheCurrentProject = mel.eval("$temp=$gCacheCurrentProject")
		gNclothCacheAutomaticName = mel.eval("$temp=$gNclothCacheAutomaticName")
	except:
		pass

	#if not gCacheCurrentProject:
	#	gCacheCurrentProject = cmds.workspace(q=True, rd=True)
	#	if 'diskCache' in cmds.workspace(q=True, frl=True):
	#		gCacheCurrentProject = os.path.join(gCacheCurrentProject, cmds.workspace(fre='diskCache'),	\
	#			os.path.basename(cmds.file(q=True, sn=True)).split('.')[0])

	distrib = "OneFilePerFrame"
	if cmds.optionVar(q='nclothCacheDistrib') == 2:
		distrib = "OneFile"

	directory = cmds.optionVar(query='nclothCacheDirName')
	if directory == gCacheCurrentProject:
		directory = ""

	try:
		mel.eval("nclothCacheNameChanged()")
	except:
		pass

	fileName = cmds.optionVar(query="nclothCacheName")
	if fileName == gNclothCacheAutomaticName:
		fileName = ""
	
	prefix = 0
	if cmds.optionVar(ex='nclothCacheUsePrefix'):
		if fileName:
			prefix = cmds.optionVar(q='nclothCacheUsePrefix')

	if action == "merge":
		if cmds.optionVar(q='nclothCacheMergeDelete'):
			action = "mergeDelete"
	
	inherit = 0
	if action == "replace":
		inherit = cmds.optionVar(q='nclothCacheInheritModifications')

	if action == "append":
		return	"doAppendNclothCache " +	\
			str(cmds.optionVar(q='appendNclothCacheTimeRange')) + " " +	\
			str(cmds.optionVar(q='appendNclothCacheStartTime')) + " " +	\
			str(cmds.optionVar(q='appendNclothCacheEndTime')) + " " +	\
			str(cmds.optionVar(q='appendNclothCacheSimulationRate')) + " " +	\
			str(cmds.optionVar(q='appendNclothCacheSampleMultiplier'))

	return  "doCreateNclothCache 4 { \"" + str(cmds.optionVar(q='nclothCacheTimeRange')) + "\", " +	\
			"\"" + str(cmds.optionVar(q='nclothCacheStartTime')) + "\", " +	\
			"\"" + str(cmds.optionVar(q='nclothCacheEndTime')) +  "\", " +	\
			"\"" + str(distrib) + "\", " +	\
			"\"" + str(cmds.optionVar(q='nclothRefresh')) + "\", " +	\
			"\"" + directory + "\"," +		\
			"\"" + str(cmds.optionVar(q='nclothCachePerGeometry')) + "\"," +	\
			"\"" + fileName + "\"," +		\
			"\"" + str(prefix) + "\", " +		\
			"\"" + action + "\", " +		\
			"\"0\", " +						\
			"\"" + str(cmds.optionVar(q='nclothCacheSimulationRate')) + "\", " +		\
			"\"" + str(cmds.optionVar(q='nclothCacheSampleMultiplier')) +  "\"," +	\
			"\"" + str(inherit) + "\"," +		\
			"\"" + str(cmds.optionVar(q='nclothCacheAsFloats')) + "\"" +		\
			" } "


def	batchSimulate(*args, **keywords):
	if 'cache' not in keywords.keys():
		raise Exception, "argument error"
	elif keywords['cache'] not in cacheOptions():
		raise Exception, "argument error"

	if args:
		cmds.select(args, r=True)

	startNow = True
	shutdown = False
	if 'startNow' in keywords: startNow = keywords['startNow']
	if 'shutdown' in keywords: shutdown = keywords['shutdown']

	if not cmds.ls(sl=True) or not cmds.listRelatives(type='mesh', f=True, s=True, ni=True):
		raise Exception, "no garment selected"

	garments = []
	for s in cmds.listRelatives(type='mesh', f=True, s=True, ni=True):
		nc = jc.helper.findTypeInHistory(s, type="nCloth")
		if not nc:
			raise Exception, "selected object is not an ncloth object"
		garments.append(cmds.listRelatives(s, p=True, f=True)[0])

	if not garments:
		raise Exception, "no garment selected"

	mayabatch = os.path.join(os.path.abspath(os.getenv('MAYA_LOCATION')), "bin")
	if cmds.about(nt=True):
		mayabatch = os.path.join(mayabatch, "mayabatch.exe")
	else:
		mayabatch = os.path.join(mayabatch, "maya")

	projectDirectory = cmds.workspace(q=True, rd=True)

	currentScene = os.path.abspath(cmds.file(q=True, sn=True))

	def f(x): return x.isalpha()
	melProc = "".join(filter(f, os.path.split(currentScene)[1].split('.')[0]))+"_"+"_".join(garments).replace(':','').replace('|','')+"_cache"

	batchCmdPath = projectDirectory
	if 'scene' in cmds.workspace(q=True, frl=True):
		batchCmdPath = os.path.join(projectDirectory, cmds.workspace(fre='scene'), melProc)
	if cmds.about(nt=True):
		batchCmdPath += ".bat"

	melScriptPath = projectDirectory
	if 'mel' in cmds.workspace(q=True, frl=True):
		melScriptPath = os.path.join(projectDirectory, cmds.workspace(fre='mel'))
	melScriptPath = os.path.join(melScriptPath, melProc+".mel")

	quote = ""
	if cmds.about(nt=True):
		quote = '"'
	batchCmd = " -proj "+quote+projectDirectory+quote+" -file "+quote+currentScene+quote+" -script "+quote+melScriptPath+quote+" -command \""+melProc+"();\"\n"
	if cmds.about(nt=True):
		batchCmd = '"'+mayabatch+'"' + batchCmd
	else:
		batchCmd = mayabatch + " -batch" + batchCmd

	if shutdown:
		if cmds.about(nt=True):
			batchCmd += "shutdown -s"
		else:
			batchCmd += "shutdown -P 0"

	melScript = "global proc "+melProc+"()\n"
	melScript += "{\n"
	melScript += "\tselect -r "+" ".join(garments)+";\n"
	#melScript += '\tdoCreateNclothCache 4 { "3", "1", "100", "OneFile", "1", "","0","","0", "add", "0", "1", "1","0","1" } ;\n'
	if keywords['cache'] == cacheOptions()[0]:
		melScript += "\t"+__assembleCmd("add")+";\n"
	elif keywords['cache'] == cacheOptions()[1]:
		melScript += "\t"+__assembleCmd("replace")+";\n"
	elif keywords['cache'] == cacheOptions()[2]:
		melScript += "\t"+__assembleCmd("merge")+";\n"
	elif keywords['cache'] == cacheOptions()[3]:
		melScript += "\t"+__assembleCmd("append")+";\n"
	melScript += "}"

	# save files
	file = open(batchCmdPath, "w+")
	if not cmds.about(nt=True):
		file.write("#!/bin/bash\n")
	file.write(batchCmd)
	file.close()
	if not cmds.about(nt=True):
		os.chmod(batchCmdPath, 511)
	file = open(melScriptPath, "w+")
	file.write(melScript)
	file.close()

	# check paths existence
	if not os.path.exists(mayabatch):
		raise Exception, "missing file "+mayabatch
	if not os.path.exists(batchCmdPath):
		raise Exception, "missing file "+batchCmdPath
	if not os.path.exists(melScriptPath):
		raise Exception, "missing file "+melScriptPath
	if not os.path.exists(currentScene):
		raise Exception, "missing file "+currentScene

	print "batch file: "+batchCmdPath
	print "mel file: "+melScriptPath

	if startNow:
		pid = os.spawnl(os.P_NOWAIT, batchCmdPath,  batchCmdPath)
		print "start process of pid "+str(pid)


def	cacheOptions():
	return [ "Create New", "Replace", "Merge", "Append" ]


def	batchRename(*args, **keywords):
	if 'prefix' not in keywords.keys():
		raise Exception, "argument error"

	if args:
		cmds.select(args)

	jc.helper.batchRename(prefix=keywords['prefix'])




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

		i = jc.menu.commandItem(m, __moduleName+".garmentBuilder", "Garment Builder", annotation="Open Garment Builder")
		jc.menu.listOption(i, "garment", garmentOptions()[0], garmentOptions)

		#i = jc.menu.commandItem(m, __moduleName+".buildGarmentFromFile", "Build Garment From File", annotation="Open File")

		jc.menu.dividerItem(m)

		i = jc.menu.commandItem(m, __moduleName+".createArcLengthDimension", "Create Arc Length Dimension", annotation="Select curves")

		i = jc.menu.commandItem(m, __moduleName+".createPattern", "Create Pattern", annotation="Select pattern curves and locator")
		jc.menu.booleanOption(i, "mirror", True)
		jc.menu.floatOption(i, "resolution", 1, share=True)
		jc.menu.booleanOption(i, "reverse Normal", False)

		i = jc.menu.commandItem(m, __moduleName+".createGarment", "Create Garment", annotation="Select pattern(s)")
		jc.menu.stringOption(i, "prefix", "")
		jc.menu.listOption(i, "nCloth Preset", getNClothPresetsCallback()[0], getNClothPresetsCallback)

		i = jc.menu.commandItem(m, __moduleName+".createStitch", "Create Stitch", annotation="Select pattern curves and destination curve")
		jc.menu.integerOption(i, "number Of Joints", 10)
		jc.menu.booleanOption(i, "rebuild Destination Curve", False)
		jc.menu.booleanOption(i, "mirror", True)
		jc.menu.booleanOption(i, "stretch", False)
		jc.menu.booleanOption(i, "bind", True)

		i = jc.menu.commandItem(m, __moduleName+".createWeldConstraint", "Create Weld Constraint", annotation="Select pattern curves")

		i = jc.menu.commandItem(m, __moduleName+".rebuildUV", "Rebuild UV", annotation="Select garments")

		i = jc.menu.commandItem(m, __moduleName+".attachButtons", "Attach Buttons", annotation="Select garment and buttons")
		jc.menu.listOption(i, "button Type", buttonOptions()[0], buttonOptions)
		jc.menu.listOption(i, "nCloth Preset", getNClothPresetsCallback()[0], getNClothPresetsCallback)
		jc.menu.stringOption(i, "group Name", "buttons")

		i = jc.menu.commandItem(m, __moduleName+".setKeyframes", "Set Keyframes", annotation="Select garment")
		jc.menu.checkboxOption(i, "set Keyframes For", setKeyframesOptions(), setKeyframesOptions)
		jc.menu.integerOption(i, "stitch Start Time", 1, share=True)
		jc.menu.integerOption(i, "stitch End Time", 40, share=True)
		jc.menu.integerOption(i, "turn On Constraints Time", 50, share=True)
		jc.menu.integerOption(i, "turn Off Input Mesh Attract Time", 60, share=True)

		i = jc.menu.commandItem(m, __moduleName+".matchJoints", "Match Joints", annotation="Select joint chains")
		jc.menu.integerOption(i, "stitch Start Time", 1, share=True)
		jc.menu.integerOption(i, "stitch End Time", 40, share=True)
		jc.menu.integerOption(i, "twist Root", 180)

		i = jc.menu.commandItem(m, __moduleName+".attachAdjacentStitches", "Attach Adjacent Stitches", annotation="Select joint chains")
		jc.menu.integerOption(i, "stitch Start Time", 1, share=True)
		jc.menu.integerOption(i, "stitch End Time", 40, share=True)

		i = jc.menu.commandItem(m, __moduleName+".deleteGarment", "Delete Garment", annotation="Select garment")

		i = jc.menu.commandItem(m, __moduleName+".duplicateGarment", "Duplicate Garment", annotation="Select garment")

		i = jc.menu.commandItem(m, __moduleName+".attachLayer", "Attach Layer", annotation="Select garment")
		jc.menu.listOption(i, "layer", layerOptions()[0], layerOptions)

		i = jc.menu.commandItem(m, __moduleName+".batchSimulate", "Batch Simulate", annotation="Select garment")
		jc.menu.listOption(i, "cache", cacheOptions()[0], cacheOptions)
		jc.menu.booleanOption(i, "start Now", True)
		jc.menu.booleanOption(i, "shutdown", False)

		jc.menu.dividerItem(m)

		i = jc.menu.commandItem(m, __moduleName+".createButtonConstraint", "Create Button Constraint", annotation="Select two continuous edges on a garment")
		jc.menu.integerOption(i, "interval", 6)
		jc.menu.booleanOption(i, "flip", False)

		i = jc.menu.commandItem(m, __moduleName+".createZipConstraint", "Create Zip Constraint", annotation="Select two continuous edges on a garment")
		jc.menu.booleanOption(i, "flip", False)

		i = jc.menu.commandItem(m, __moduleName+".createHingeConstraint", "Create Hinge Constraint", annotation="Select two continuous edges on a garment")
		jc.menu.booleanOption(i, "flip", False)
		jc.menu.booleanOption(i, "rotate", False)

		i = jc.menu.commandItem(m, __moduleName+".deleteGroupConstraint", "Delete Group Constraint", annotation="Select constraint group(s)")

		jc.menu.dividerItem(m)

		i = jc.menu.commandItem(m, __moduleName+".batchRename", "Batch Rename", annotation="Select object(s)")
		jc.menu.stringOption(i, "prefix", "")
