# if you have an existing userSetup.py file you will need to append
# this code to make all the jc modules available
# cut and paste the contents of this file into your existing userSetup.py
# and then restart maya

import maya.utils, maya.cmds
import sys

# sys.path.append( '<your scripts directory>' )

import jc.helper, jc.files, jc.menu, jc.character, jc.hair, jc.clothes


# unmark the following lines to enable testMenu upon startup
# import testMenu
# maya.utils.executeDeferred( testMenu.doMenu ) 

# unmark the following line to enable jc menu upon startup
# maya.utils.executeDeferred( jc.menu.startup ) 

#def registerPlugin():
#	maya.cmds.loadPlugin('jcClothes.mll', qt=1 )
#	maya.cmds.loadPlugin('jcBody.mll', qt=1 )
#maya.utils.executeDeferred( registerPlugin )
