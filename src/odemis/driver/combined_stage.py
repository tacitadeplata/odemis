# -*- coding: utf-8 -*-
'''
Created on 9 Jul 2014

@author: Kimon Tsitsikas

Copyright © 2014 Kimon Tsitsikas, Delmic

This file is part of Odemis.

Odemis is free software: you can redistribute it and/or modify it under the terms
of the GNU General Public License version 2 as published by the Free Software
Foundation.

Odemis is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY;
without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR
PURPOSE. See the GNU General Public License for more details.

You should have received a copy of the GNU General Public License along with
Odemis. If not, see http://www.gnu.org/licenses/.
'''

from __future__ import division

from Pyro4.core import isasync
from odemis.acq import ConvertStage
from odemis import model
import math
import numpy

class CombinedStage(model.Actuator):
    """
    Wrapper stage that takes as children the SEM sample stage and the 
    ConvertStage. For each move to be performed CombinedStage moves, at the same 
    time, both stages.
    """
    def __init__(self, name, role, children, axes, scale, rotation, offset):
        """
        children (dict str -> actuator): name to objective lens actuator
        axes (list of string): names of the axes for x and y
        scale (tuple of floats): scale factor from SEM to optical
        rotation (float in degrees): rotation factor
        offset (tuple of floats): offset factor #m, m
        """
        assert len(axes) == 2
        if len(children) != 1:
            raise ValueError("StageConverted needs 1 child")

        self._child = children.values()[0]
        self._axes_child = {"x": axes[0], "y": axes[1]}
        self._scale = scale
        self._rotation = math.radians(rotation)
        self._offset = offset

        # Axis rotation
        self._R = numpy.array([[math.cos(self._rotation), -math.sin(self._rotation)],
                         [math.sin(self._rotation), math.cos(self._rotation)]])
        # Scaling between the axis
        self._L = numpy.array([[self._scale[0], 0],
                         [0, self._scale[1]]])
        # Offset between origins of the coordinate systems
        self._O = numpy.transpose([self._offset[0], self._offset[1]])

        axes_def = {"x": self._child.axes[axes[0]],
                    "y": self._child.axes[axes[1]]}
        model.Actuator.__init__(self, name, role, axes=axes_def)

        # RO, as to modify it the client must use .moveRel() or .moveAbs()
        self.position = model.VigilantAttribute(
                                    {"x": 0, "y": 0},
                                    unit="m", readonly=True)
        # it's just a conversion from the child's position
        self._child.position.subscribe(self._updatePosition, init=True)

        # No speed, not needed
        # self.speed = model.MultiSpeedVA(init_speed, [0., 10.], "m/s")

    def _convertPosFromChild(self, pos_child):
        # Object lens position vector
        Q = numpy.transpose([pos_child[0], pos_child[1]])
        # Transform to coordinates in the reference frame of the sample stage
        p = numpy.add(self._O, numpy.invert(self._R).dot(numpy.invert(self._L)).dot(Q))
        return p.tolist()

    def _convertPosToChild(self, pos):
        # Sample stage position vector
        P = numpy.transpose([pos[0], pos[1]])
        # Transform to coordinates in the reference frame of the objective stage
        q = self._L.dot(self._R).dot(numpy.subtract(P, self._O))
        return q.tolist()

    def _updatePosition(self, pos_child):
        """
        update the position VA when the child's position is updated
        """
        # it's read-only, so we change it via _value
        vpos_child = [pos_child[self._axes_child["x"]],
                      pos_child[self._axes_child["y"]]]
        vpos = self._convertPosFromChild(vpos_child)
        self.position._value = {"x": vpos[0],
                                "y": vpos[1]}
        self.position.notify(self.position.value)

    @isasync
    def moveRel(self, shift):

        # shift is a vector, conversion is identical to a point
        vshift = [shift.get("x", 0), shift.get("y", 0)]
        vshift_child = self._convertPosToChild(vshift)

        shift_child = {self._axes_child["x"]: vshift_child[0],
                       self._axes_child["y"]: vshift_child[1]}
        f = self._child.moveRel(shift_child)
        return f

    # For now we don't support moveAbs(), not needed
    def moveAbs(self, pos):
        raise NotImplementedError("Do you really need that??")

    def stop(self, axes=None):
        # This is normally never used (child is directly stopped)
        self._child.stop()
