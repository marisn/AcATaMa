# -*- coding: utf-8 -*-
"""
/***************************************************************************
 AcATaMa
                                 A QGIS plugin
 AcATaMa is a Qgis plugin for Accuracy Assessment of Thematic Maps
                              -------------------
        copyright            : (C) 2017 by Xavier Corredor Llano, SMBYC
        email                : xcorredorl@ideam.gov.co
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import os
from PyQt4 import QtGui, uic
from PyQt4.QtCore import QSettings, Qt, pyqtSlot, QTimer
from qgis.core import QgsGeometry, QgsPoint, QGis
from qgis.gui import QgsMapCanvas, QgsMapCanvasLayer, QgsMapToolPan, QgsRubberBand, QgsVertexMarker
from qgis.utils import iface

from AcATaMa.core.dockwidget import update_layers_list, get_current_layer_in, load_layer_in_qgis
from AcATaMa.core.utils import block_signals_to


class Marker():
    def __init__(self, canvas):
        self.marker = None
        self.canvas = canvas

    def show(self, in_point):
        """Show marker for the respective view widget"""
        if self.marker is None:
            self.marker = QgsVertexMarker(self.canvas)
            self.marker.setIconSize(18)
            self.marker.setPenWidth(2)
            self.marker.setIconType(QgsVertexMarker.ICON_CROSS)
        self.marker.setCenter(in_point.QgsPnt)
        self.marker.updatePosition()

    def remove(self):
        """Remove marker for the respective view widget"""
        self.canvas.scene().removeItem(self.marker)
        self.marker = None

    def highlight(self):
        curr_ext = self.canvas.extent()

        left_point = QgsPoint(curr_ext.xMinimum(), curr_ext.center().y())
        right_point = QgsPoint(curr_ext.xMaximum(), curr_ext.center().y())

        top_point = QgsPoint(curr_ext.center().x(), curr_ext.yMaximum())
        bottom_point = QgsPoint(curr_ext.center().x(), curr_ext.yMinimum())

        horiz_line = QgsGeometry.fromPolyline([left_point, right_point])
        vert_line = QgsGeometry.fromPolyline([top_point, bottom_point])

        cross_rb = QgsRubberBand(self.canvas, QGis.Line)
        cross_rb.setColor(QtGui.QColor(255, 0, 0))
        cross_rb.reset(QGis.Line)
        cross_rb.addGeometry(horiz_line, None)
        cross_rb.addGeometry(vert_line, None)

        QTimer.singleShot(600, cross_rb.reset)
        self.canvas.refresh()


class RenderWidget(QtGui.QWidget):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.setupUi()
        self.layer = None
        self.marker = Marker(self.canvas)

    def setupUi(self):
        gridLayout = QtGui.QGridLayout(self)
        gridLayout.setContentsMargins(0, 0, 0, 0)
        self.canvas = QgsMapCanvas()
        self.canvas.setCanvasColor(QtGui.QColor(255, 255, 255))
        self.canvas.setStyleSheet("border: 0px;")
        settings = QSettings()
        self.canvas.enableAntiAliasing(settings.value("/qgis/enable_anti_aliasing", False, type=bool))
        self.canvas.useImageToRender(settings.value("/qgis/use_qimage_to_render", False, type=bool))
        # action zoom
        action = settings.value("/qgis/wheel_action", 0, type=int)
        zoomFactor = settings.value("/qgis/zoom_factor", 2.0, type=float)
        self.canvas.setWheelAction(QgsMapCanvas.WheelAction(action), zoomFactor)
        # action pan
        self.toolPan = QgsMapToolPan(self.canvas)
        self.canvas.setMapTool(self.toolPan)
        # toggled render view widget
        self.parent().OnOff_RenderView.toggled.connect(self.toggle_render)

        gridLayout.addWidget(self.canvas)

    def render_layer(self, layer):
        with block_signals_to(self):
            if not layer:
                self.canvas.clear()
                self.canvas.refreshAllLayers()
                self.layer = None
                # set status for view widget
                self.parent().is_active = False
                return
            self.canvas.setLayerSet([QgsMapCanvasLayer(self.parent().sampling_layer), QgsMapCanvasLayer(layer)])
            self.update_crs()

            # set init extent from other view if any is activated else set layer extent
            from AcATaMa.gui.classification_dialog import ClassificationDialog
            others_view = [(view_widget.render_widget.canvas.extent(), view_widget.current_scale_factor) for view_widget
                           in ClassificationDialog.view_widgets if view_widget.is_active]
            if others_view:
                extent, scale = others_view[0]
                extent.scale(1 / scale)
                self.canvas.setExtent(extent)
            else:
                self.canvas.setExtent(layer.extent())

            self.canvas.refresh()
            self.layer = layer
            # show marker
            self.marker.show(ClassificationDialog.current_sample)
            # set status for view widget
            self.parent().is_active = True

    def update_crs(self):
        renderer = iface.mapCanvas().mapRenderer()
        self.canvas.mapRenderer().setDestinationCrs(renderer.destinationCrs())
        self.canvas.mapRenderer().setMapUnits(renderer.mapUnits())
        # transform enable
        self.canvas.mapRenderer().setProjectionsEnabled(True)

    def set_extents_and_scalefactor(self, extent):
        with block_signals_to(self.canvas):
            self.canvas.setExtent(extent)
            self.canvas.zoomByFactor(self.parent().scaleFactor.value())

    def layer_properties(self):
        if not self.layer:
            return
        # call properties dialog
        iface.showLayerProperties(self.layer)

        self.parent().activateWindow()
        self.canvas.refresh()

    def toggle_render(self, enabled):
        self.canvas.setRenderFlag(enabled)


# plugin path
plugin_folder = os.path.dirname(os.path.dirname(__file__))
FORM_CLASS, _ = uic.loadUiType(os.path.join(
    plugin_folder, 'ui', 'classification_view_widget.ui'))


class ClassificationViewWidget(QtGui.QWidget, FORM_CLASS):
    def __init__(self, parent=None):
        QtGui.QWidget.__init__(self, parent)
        self.id = None
        self.is_active = False
        self.current_scale_factor = 1.0
        self.qgs_main_canvas = iface.mapCanvas()
        self.setupUi(self)

    def setup_view_widget(self, sampling_layer):
        self.sampling_layer = sampling_layer
        # render layer actions
        update_layers_list(self.selectRenderFile, "any", ignore_layers=[self.sampling_layer])
        # handle connect when the list of layers changed
        self.qgs_main_canvas.layersChanged.connect(
            lambda: update_layers_list(self.selectRenderFile, "any", ignore_layers=[self.sampling_layer]))
        self.selectRenderFile.currentIndexChanged.connect(
            lambda: self.render_widget.render_layer(get_current_layer_in(self.selectRenderFile)))
        # call to browse the render file
        self.browseRenderFile.clicked.connect(lambda: self.fileDialog_browse(
            self.selectRenderFile,
            dialog_title=self.tr(u"Select the file for this view"),
            dialog_types=self.tr(u"Raster or vector files (*.tif *.img *.shp);;All files (*.*)"),
            layer_type="any"))

        # zoom scale factor
        self.scaleFactor.valueChanged.connect(self.scalefactor_changed)
        # edit layer properties
        self.layerProperties.clicked.connect(self.render_widget.layer_properties)
        # action for synchronize all view extent
        self.render_widget.canvas.extentsChanged.connect(self.extent_changed)

    @pyqtSlot()
    def fileDialog_browse(self, combo_box, dialog_title, dialog_types, layer_type):
        file_path = QtGui.QFileDialog.getOpenFileName(self, dialog_title, "", dialog_types)
        if file_path != '' and os.path.isfile(file_path):
            # load to qgis and update combobox list
            filename = load_layer_in_qgis(file_path, layer_type)
            update_layers_list(combo_box, layer_type, ignore_layers=[self.sampling_layer])
            selected_index = combo_box.findText(filename, Qt.MatchFixedString)
            combo_box.setCurrentIndex(selected_index)

            self.render_widget.canvas.setExtent(get_current_layer_in(combo_box).extent())
            self.render_widget.canvas.refresh()

    @pyqtSlot()
    def extent_changed(self):
        if self.is_active:
            from AcATaMa.gui.classification_dialog import ClassificationDialog
            view_extent = self.render_widget.canvas.extent()
            view_extent.scale(1/self.current_scale_factor)

            # set extent and scale factor for all view activated except this view
            for view_widget in ClassificationDialog.view_widgets:
                if view_widget.is_active and view_widget != self:
                    view_widget.render_widget.set_extents_and_scalefactor(view_extent)

    @pyqtSlot()
    def scalefactor_changed(self):
        if self.is_active:
            # adjust view with the original extent (scale factor=1)
            # and with the new scale factor
            view_extent = self.render_widget.canvas.extent()
            view_extent.scale(1 / self.current_scale_factor)
            self.render_widget.set_extents_and_scalefactor(view_extent)
            # save the new scale factor
            self.current_scale_factor = self.scaleFactor.value()