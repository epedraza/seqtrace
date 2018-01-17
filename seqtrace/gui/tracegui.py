#!/usr/bin/python
# Copyright (C) 2018 Brian J. Stucky
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


from seqtrace.core import sequencetrace
from seqtrace.core import seqwriter

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk
from gi.repository import Gdk
import cairo
from gi.repository import Pango, PangoCairo
import os.path

# Get the Gdk.RGBA convenience functions.
from colorfuncs import parseHTMLColorStr, colorFromHSV


class SequenceTraceViewer:
    def __init__(self, sequencetrace):
        self.min_height = 100
        self.preferred_height = 200

        self.drawingarea = Gtk.DrawingArea()
        self.drawingarea.set_size_request(-1, self.min_height)

        self.seqt = sequencetrace

        # Initialize drawing settings.
        self.tracecolors = {
            'A': parseHTMLColorStr('#009000'),    # green
            'C': parseHTMLColorStr('#0000ff'),    # blue
            'G': parseHTMLColorStr('#000000'),    # black
            'T': parseHTMLColorStr('#ff0000'),    # red
            'W': parseHTMLColorStr('#804800'),    # mix of A and T
            'S': parseHTMLColorStr('#000080'),    # mix of C and G
            'M': parseHTMLColorStr('#004880'),    # mix of A and C
            'K': parseHTMLColorStr('#800000'),    # mix of G and T
            'R': parseHTMLColorStr('#004800'),    # mix of A and G
            'Y': parseHTMLColorStr('#800080'),    # mix of C and T
            'B': parseHTMLColorStr('#550055'),    # mix of C, G, and T
            'D': parseHTMLColorStr('#553000'),    # mix of A, G, and T
            'H': parseHTMLColorStr('#553055'),    # mix of A, C, and T
            'V': parseHTMLColorStr('#003055'),    # mix of A, C, and G
            'N': parseHTMLColorStr('#999')        # gray
        }
        # Set up colors with an alpha channel to use for the lines from
        # the base calls to the trace peaks.
        self.pklinecolors = {}
        self.pklinecolors['A'] = (
            self.tracecolors['A'].red, self.tracecolors['A'].green,
            self.tracecolors['A'].blue, 0.84
        )
        self.pklinecolors['C'] = (
            self.tracecolors['C'].red, self.tracecolors['C'].green,
            self.tracecolors['C'].blue, 0.6
        )
        self.pklinecolors['G'] = (
            self.tracecolors['G'].red, self.tracecolors['G'].green,
            self.tracecolors['G'].blue, 0.6
        )
        self.pklinecolors['T'] = (
            self.tracecolors['T'].red, self.tracecolors['T'].green,
            self.tracecolors['T'].blue, 0.68
        )

        self.bottom_margin = 2
        self.bcpadding = 4

        self.show_confidence = True

        self.sigmax = sequencetrace.getMaxTraceVal() + (sequencetrace.getMaxTraceVal() / 12)

        self.bclayout = Pango.Layout(self.drawingarea.create_pango_context())
        self.bcfontdesc = self.bclayout.get_context().get_font_description().copy()
        self.setFontSize(10)

        self.drawingarea.connect('draw', self.updatedisplay)

        self.highlighted = self.seqt.getNumBaseCalls()

    def getDefaultHeight(self):
        return self.min_height

    def getPreferredHeight(self):
        return self.preferred_height

    def getSequenceTrace(self):
        return self.seqt

    def getWidget(self):
        return self.drawingarea

    def getYScaleMax(self):
        return self.sigmax

    def setYScaleMax(self, new_yscalemax):
        if new_yscalemax <= 0:
            raise Exception

        self.sigmax = new_yscalemax

        # queue a redraw of the visible part of the drawing area
        #vis_region = self.window.get_visible_region()
        #print vis_region.get_clipbox()
        #self.window.invalidate_region(vis_region, False)

        # the following methods also work, and it appears that GTK is able to automatically
        # clip the update region to only the visible portion of the widget
        width, height = self.drawingarea.window.get_size()
        #print width, height
        self.drawingarea.window.invalidate_rect((0, 0, width, height), False)
        #self.queue_draw_area(0, 0, width, height)

    def setShowConfidence(self, newval):
        self.show_confidence = newval

        # queue a redraw of the window
        width, height = self.drawingarea.window.get_size()
        self.drawingarea.window.invalidate_rect((0, 0, width, height), False)

    def setFontSize(self, size):
        # set up base call font properties
        self.bcfontdesc.set_size(size*Pango.SCALE)
        self.bclayout.set_font_description(self.bcfontdesc)
        self.bclayout.set_text('A', 1)
        self.bcheight = self.bclayout.get_pixel_size()[1] + (self.bcpadding*2)

    def updatedisplay(self, da, cr):
        dwin = self.drawingarea.get_window()

        #print '(', event.area.x, ',', event.area.y
        #startx = event.area.x
        #dwidth = event.area.width
        startx = 0
        height = self.drawingarea.get_allocated_height()
        dwidth = self.drawingarea.get_allocated_width()
        if startx > 0:
            # Becase the Cairo coordinates are shifted by +0.5 for the trace
            # drawing, make sure that we have sufficient overlap with previous
            # drawing operations so that we don't get breaks in the antialiasing.
            startx -= 1
            dwidth += 1
        #print startx, dwidth

        # Create the Cairo context.
        #cr = dwin.cairo_create()
        cr.set_antialias(cairo.ANTIALIAS_DEFAULT)
        cr.set_line_join(cairo.LINE_JOIN_ROUND)

        self.eraseda(height, startx, dwidth, cr)
        self.drawBaseCalls(dwidth, height, startx, dwidth, cr)
        self.drawTrace(dwin, cr, startx=startx, dwidth=dwidth)
        if self.highlighted != self.seqt.getNumBaseCalls():
            self.highlightBaseInternal(self.highlighted);

    def eraseda(self, height, startx, dwidth, cr):
        cr.set_source_rgba(1.0, 1.0, 1.0)
        cr.rectangle(startx, 0, dwidth, height)
        cr.fill()

    def drawTrace(self, dwin, cr, startx=0, dwidth=0):
        """
        Draw the trace lines using Cairo.  Note that because we are drawing
        1-pixel width lines, 0.5 is added to the x and y coordinates, which
        guarantees that the lines are drawn in the same position as with
        the regular GTK drawing routines and also ensures that vertical and
        horizontal lines are exactly 1 pixel wide.
        """
        width = self.drawingarea.get_allocated_width()
        height = self.drawingarea.get_allocated_height()
        if dwidth == 0:
            dwidth = width

        drawheight = height - self.bottom_margin - self.bcheight

        cr.set_line_width(1)

        samps = self.seqt.getTraceLength()
        startsamp = (startx * samps) / width
        endsamp = int((float(startx+dwidth) * samps) / width + 0.5)
        if endsamp < (samps-1):
            endsamp += 2

        yscale = float(drawheight) / self.sigmax
        xscale = float(width) / samps

        for base in ('A','C','G','T'):
            cr.set_source_rgba(*self.tracecolors[base])
            data = self.seqt.getTraceSamples(base)

            oldx = int(startsamp * xscale)
            oldy = int((self.sigmax - data[startsamp]) * yscale + 0.5)
            for cnt in range(startsamp, endsamp):
                x = int(cnt * xscale)
                y = int((self.sigmax - data[cnt]) * yscale + 0.5)
                cr.move_to(oldx+0.5, oldy+0.5)
                cr.line_to(x+0.5, y+0.5)
                oldx = x
                oldy = y
            cr.stroke()

    def drawBaseCalls(self, width, height, startx, dwidth, cr):
        """
        Draws the base calls, confidence scores and bars, and lines from
        the base calls to the trace peaks.
        """
        if dwidth == 0:
            dwidth = width

        # Save the Cairo context settings.
        cr.save()
        cr.set_dash((1,1))
        cr.set_line_width(1)

        drawheight = height - self.bottom_margin - self.bcheight
        confbarmax = drawheight / 4
        conf_hue_best = 0.68
        conf_hue_worst = 1.0

        samps = self.seqt.getTraceLength()
        startsamp = (startx * samps) / width
        endsamp = int((float(startx+dwidth) * samps) / width + 0.5)
        if endsamp < (samps-1):
            endsamp += 2

        startbcindex = self.seqt.getPrevBaseCallIndex(startsamp)
        #print startbcindex
        endbcindex = self.seqt.getNextBaseCallIndex(endsamp)
        if endbcindex < self.seqt.getNumBaseCalls():
            endbcindex += 1
        #print endbcindex

        xscale = float(width) / samps
        yscale = float(drawheight) / self.sigmax
        y = drawheight + self.bcpadding

        confbarcolor = Gdk.RGBA()
        confbarcolor.parse('#c8c8c8')

        for index in range(startbcindex, endbcindex):
            # Get the base and position.
            base = self.seqt.getBaseCall(index)
            pos = self.seqt.getBaseCallPos(index)

            x = int(pos * xscale)

            if self.show_confidence:
                # Draw the confidence bar.
                bcconf = self.seqt.getBaseCallConf(index)
                cr.set_source_rgba(*confbarcolor)
                #hue = float(bcconf) * (conf_hue_best - conf_hue_worst) / 61 + conf_hue_worst
                #cr.set_source_rgba(*colorFromHSV(hue, 0.34, 1.0))
                cr.rectangle(x-6, 6, 12, (confbarmax*bcconf)/61)
                cr.fill()

                # Draw the confidence score.
                hue = float(bcconf) * (conf_hue_best - conf_hue_worst) / 61 + conf_hue_worst
                cr.set_source_rgba(*colorFromHSV(hue, 1.0, 0.9))
                self.bclayout.set_text(str(bcconf), -1)
                txtwidth = self.bclayout.get_pixel_size()[0]
                cr.move_to(x - (txtwidth/2), 6)
                PangoCairo.layout_path(cr, self.bclayout)
                cr.fill()

            # Draw the base.
            cr.set_source_rgba(*self.tracecolors[base])
            self.bclayout.set_text(base, 1)
            txtwidth = self.bclayout.get_pixel_size()[0]
            cr.move_to(x - (txtwidth/2), y)
            PangoCairo.layout_path(cr, self.bclayout)
            cr.fill()

            # Calculate the y coordinate of the trace location for this base and draw a line to
            # it from the base call.  It only makes sense to do this for non-ambiguous bases.
            if base in ('A', 'T', 'G', 'C'):
                traceval = self.seqt.getTraceSample(base, pos)
                ysamp = int((self.sigmax - traceval) * yscale + 0.5)

                # Draw the line to the trace.
                # As with drawing the trace lines, add 0.5 to the x coordinates to ensure
                # the lines appear in the "correct" location (with reference to the standard
                # GTK drawing routines and that they are exactly 1 pixel wide.
                cr.set_source_rgba(*self.pklinecolors[base])
                cr.move_to(x+0.5, ysamp)
                cr.line_to(x+0.5, y-(self.bcpadding/2))
                cr.stroke()

        # Restore the old Cairo context settings.
        cr.restore()

    def highlightBase(self, bindex):
        # draw the highlight, if needed
        if bindex != self.highlighted:
            if self.highlighted != self.seqt.getNumBaseCalls():
                self.highlightBaseInternal(self.highlighted)
            self.highlightBaseInternal(bindex)
            self.highlighted = bindex  
        #dwin.draw_rectangle(gc, True, x - 6, y, 12, self.bcheight)

    def highlightBaseInternal(self, bindex):
        dwin = self.drawingarea.window
        #gc = dwin.new_gc(function=Gdk.INVERT)
        gc = dwin.new_gc(function=Gdk.XOR)
        
        # yellow
        gc.set_rgb_fg_color(Gdk.color_parse('#00f'))
        # light blue
        #gc.set_rgb_fg_color(Gdk.color_parse('#f00'))

        width, height = dwin.get_size()
        drawheight = height - self.bottom_margin - self.bcheight

        samps = self.seqt.getTraceLength()
        xscale = float(width) / samps
        yscale = float(drawheight) / self.sigmax
        y = drawheight + self.bcpadding

        # check if we got a gap location
        if bindex < 0:
            if bindex == -1:
                pos = 0
            elif (bindex+1) * -1 == self.seqt.getNumBaseCalls():
                pos = samps
            else:
                p1 = self.seqt.getBaseCallPos((bindex+1) * -1)
                p2 = self.seqt.getBaseCallPos((bindex+2) * -1)
                pos = (p1 + p2) / 2
        else:
            pos = self.seqt.getBaseCallPos(bindex)
        x = int(pos * xscale)

        # draw the highlight
        if bindex < 0:
            dwin.draw_rectangle(gc, True, x - 2, 0, 5, height)
        else:
            dwin.draw_rectangle(gc, True, x - 6, 0, 12, height)
        
        #dwin.draw_rectangle(gc, True, x - 6, y, 12, self.bcheight)


class SequenceTraceViewerDecorator:
    def __init__(self, sequencetraceviewer):
        self.viewer = sequencetraceviewer

    def getViewer(self):
        return self.viewer

    def setViewer(self, sequencetraceviewer):
        self.viewer = sequencetraceviewer

    # delegate all other operations to the decorated object
    def __getattr__(self, attr):
        return getattr(self.viewer, attr)


class FwdRevSTVDecorator(SequenceTraceViewerDecorator):
    def __init__(self, sequencetraceviewer):
        SequenceTraceViewerDecorator.__init__(self, sequencetraceviewer)

        self.hbox = Gtk.HBox()

        label = Gtk.Label()
        label.set_angle(90)

        if (sequencetraceviewer.getSequenceTrace().isReverseComplemented()):
            labeltxt = 'Reverse'
        else:
            labeltxt = 'Forward'

        label.set_markup(labeltxt)

        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.IN)
        #frame.add(label)

        self.hbox.pack_start(label, False)
        self.hbox.pack_start(self.viewer.getWidget(), True, True, 0)

        self.hbox.show_all()

    def getWidget(self):
        return self.hbox


class ScrollAndZoomSTVDecorator(SequenceTraceViewerDecorator):
    def __init__(self, sequencetraceviewer):
        SequenceTraceViewerDecorator.__init__(self, sequencetraceviewer)

        self.scrolledwin = Gtk.ScrolledWindow()

        seqt = self.viewer.getSequenceTrace()

        self.zoom_100 = 2.4

        oldwidth, oldheight = self.viewer.getWidget().get_size_request()
        #oldheight = 200
        self.viewer.getWidget().set_size_request(int(seqt.getTraceLength() * self.zoom_100), oldheight)
        innerhbox = Gtk.HBox(False)
        innerhbox.pack_start(self.viewer.getWidget(), False, False, 0)
        self.scrolledwin.set_policy(Gtk.PolicyType.ALWAYS, Gtk.PolicyType.NEVER)
        self.scrolledwin.add_with_viewport(innerhbox)

    def getWidget(self):
        return self.scrolledwin

    def zoom(self, level):
        z_scale = float(level) / 100 * self.zoom_100

        # calculate the new width for the sequence trace viewer
        new_width = int(self.viewer.getSequenceTrace().getTraceLength() * z_scale)

        # calculate the new position for the scrollbar to keep the view centered
        # around its current location
        adj = self.scrolledwin.get_hadjustment()
        center = adj.get_value() + (adj.page_size / 2)
        pos = float(center) / adj.upper
        newpos = new_width * pos
        new_adjval = int(newpos - (adj.page_size / 2))
        if new_adjval < 0:
            new_adjval = 0
        elif new_adjval > (new_width - adj.page_size):
            new_adjval = new_width - adj.page_size

        # resize the sequence trace viewer
        oldwidth, oldheight = self.viewer.getWidget().get_size_request()
        self.viewer.getWidget().set_size_request(new_width, oldheight)

        # allow the resize to complete before repositioning the scrollbar
        while Gtk.events_pending():
           Gtk.main_iteration(False)
        adj.set_value(new_adjval)

    def scrollTo(self, basenum):
        adj = self.scrolledwin.get_hadjustment()
        seqt = self.viewer.getSequenceTrace()

        scend = adj.upper - adj.page_size
        # check if we got a gap position
        if basenum < 0:
            if basenum == -1:
                bpos = 0
            elif (basenum+1) * -1 == seqt.getNumBaseCalls():
                bpos = seqt.getTraceLength() - 1
            else:
                p1 = seqt.getBaseCallPos((basenum+1) * -1)
                p2 = seqt.getBaseCallPos((basenum+2) * -1)
                bpos = (p1 + p2) / 2
        else:
            bpos = seqt.getBaseCallPos(basenum)
        tlen = seqt.getTraceLength()
        x = bpos * scend / tlen
        offset = x * adj.page_size / scend
        x = x + offset - adj.page_size/2
        if x < 0:
            x = 0
        elif x > scend:
            x = scend
        #print adj.lower, adj.upper, adj.value
        adj.set_value(x)


class SequenceTraceLayout(Gtk.VBox):
    """
    Manages the layout of one or two scrollable sequence trace viewers and a
    scrollable consensus sequence viewer.  Handles communication among these
    two or three components, such as navigating the trace views by clicking on
    the consensus view and synchronized scrolling of the two trace viewers.
    Also provides a toolbar to manage the appearance of the trace viewers.
    """
    def __init__(self, scrolled_cons_viewer, seqt_viewers):
        Gtk.VBox.__init__(self)
        self.consv = scrolled_cons_viewer

        self.seqt_viewers = seqt_viewers
        self.selected_seqtv = 0

        self.zoom_levels = [25, 50, 75, 100, 125, 150, 200, 300, 400]
        self.curr_zoom = 3

        # save the starting y-scale max values for each viewer
        self.start_yscalemax = []
        for viewer in self.seqt_viewers:
            self.start_yscalemax.append(viewer.getYScaleMax())

        self.toolbar = self.createTraceToolBar()
        #self.pack_start(toolbar, False, False)

        for viewer in self.seqt_viewers:
            self.pack_start(viewer.getWidget(), True, True, 0)
        self.pack_start(self.consv, False, True, 0)

        # If there are two trace viewers, initialize synchronized scrolling.
        if len(self.seqt_viewers) == 2:
            # Initialize the synchronized scrolling when the VBox requests to be
            # mapped to the display so that we get the correct adjustment values.
            self.connect('map', self.initializeLockedScrolling)
        else:
            self.scroll_locked = False

        # Register callbacks for the consensus sequence viewer.
        self.consv.getConsensusSequenceViewer().registerObserver('alignment_clicked', self.alignmentClicked)

        self.connect('destroy', self.destroyed)

    def alignmentClicked(self, seqnum, seq1index, seq2index):
        # If there are two trace viewers and their scrolling is synchronized,
        # unlock them before jumping to the clicked position in the alignment.
        relock = self.scroll_locked
        if self.scroll_locked:
            self.unlockScrolling()

        #print seqnum, seq1index, seq2index
        self.seqt_viewers[0].scrollTo(seq1index)
        self.seqt_viewers[0].getViewer().highlightBase(seq1index)
        if len(self.seqt_viewers) == 2:
            self.seqt_viewers[1].scrollTo(seq2index)
            self.seqt_viewers[1].getViewer().highlightBase(seq2index)

        # If scroll synchronization was initially enabled, relock the scrollbars.
        if relock:
            self.lockScrolling()

    def initializeLockedScrolling(self, widget):
        """
        Initializes synchronized scrolling for two trace viewers.  Initially locks
        the traces at the location of the first shared position in the alignment.
        This does not result in perfect matching throughout the traces, but is still
        more useful than initially locking them both at their beginnings.
        """
        # Create lists for the scroll adjustments and signal handler IDs.
        self.adjs = []
        self.adj_hids = []

        # Retrieve the scroll adjustments and set up the event handlers.
        self.adjs.append(self.seqt_viewers[0].scrolledwin.get_hadjustment())
        self.adj_hids.append(self.adjs[0].connect('value_changed', self.traceScrolled, 0))

        self.adjs.append(self.seqt_viewers[1].scrolledwin.get_hadjustment())
        self.adj_hids.append(self.adjs[1].connect('value_changed', self.traceScrolled, 1))

        # A list to track the offsets between the two scroll adjustments when
        # they are locked together.
        self.adj_offsets = [0.0, 0.0]

        csb = self.consv.getConsensusSequenceViewer().getConsensSeqBuilder()
        seq0 = csb.getAlignedSequence(0)
        seq1 = csb.getAlignedSequence(1)

        # Get the positions of the first overlapping bases in the alignment (i.e., the start
        # of the left end gap).
        lgindex = csb.getLeftEndGapStart()

        # Verify that there is actually a left end gap and overlapping bases.
        if lgindex > 0 and seq0[lgindex] != '-' and seq1[lgindex] != '-':
            # Figure out which trace has the left end gap.
            if seq0[lgindex - 1] == '-':
                seq0index = 0
                seq1index = lgindex
            else:
                seq0index = lgindex
                seq1index = 0
                
            seqt0 = self.seqt_viewers[0].getSequenceTrace()
            seqt1 = self.seqt_viewers[1].getSequenceTrace()

            # Get the locations of the bases in each trace.
            bpos0 = float(seqt0.getBaseCallPos(seq0index)) / seqt0.getTraceLength() * self.adjs[0].upper
            bpos1 = float(seqt1.getBaseCallPos(seq1index)) / seqt1.getTraceLength() * self.adjs[1].upper
        else:
            # Either there is no left end gap or no overlapping bases, so just
            # set the offsets to 0.
            bpos0 = bpos1 = 0

        # Set the starting offsets.
        self.adj_offsets[0] = bpos0 - bpos1
        self.adj_offsets[1] = bpos1 - bpos0
        #self.adj_offsets = [0.0, 0.0]

        self.scroll_locked = True

    def lockScrolling(self):
        if self.scroll_locked:
            return

        self.adjs[0].handler_unblock(self.adj_hids[0])
        self.adjs[1].handler_unblock(self.adj_hids[1])

        # Save the offsets between the positions of the two adjustments.
        self.adj_offsets[0] = self.adjs[0].get_value() - self.adjs[1].get_value()
        self.adj_offsets[1] = self.adjs[1].get_value() - self.adjs[0].get_value()

        self.scroll_locked = True

    def unlockScrolling(self):
        if not(self.scroll_locked):
            return

        self.adjs[0].handler_block(self.adj_hids[0])
        self.adjs[1].handler_block(self.adj_hids[1])

        self.scroll_locked = False

    def traceScrolled(self, adj, index):
        #print 'min', index, adj.get_lower()
        #print 'max:', adj.get_upper()
        #print 'page size:', adj.get_page_size()
        #print adj.get_value()

        # Get the index of the other (non event-triggering) adjustment.
        index2 = (index + 1) % 2

        # Avoid triggering a cascade of events.
        self.adjs[index2].handler_block(self.adj_hids[index2])

        # Calculate the position of the other scrollbar adjustment.
        value2 = adj.get_value() - self.adj_offsets[index]

        # Update the other scroll adjustment if we're not outside of its bounds.
        if value2 >= 0.0 and value2 <= (self.adjs[index2].get_upper() - self.adjs[index2].get_page_size()):
            self.adjs[index2].set_value(value2)

        # Re-enable the signal handler for the adjustment.
        self.adjs[index2].handler_unblock(self.adj_hids[index2])

    def getTraceToolBar(self):
        return self.toolbar

    def createTraceToolBar(self):
        toolbar = Gtk.Toolbar()
        #toolbar.set_orientation(Gtk.Orientation.VERTICAL)
        #toolbar.set_icon_size(Gtk.IconSize.MENU)
        toolbar.set_icon_size(Gtk.IconSize.LARGE_TOOLBAR)
        toolbar.set_style(Gtk.ToolbarStyle.ICONS)
        toolbar.set_show_arrow(False)

        # build the zoom controls
        self.zoomin_button = Gtk.ToolButton(Gtk.STOCK_ZOOM_IN)
        self.zoomin_button.set_homogeneous(False)
        self.zoomin_button.set_tooltip_text('Zoom in')
        self.zoomin_button.connect('clicked', self.zoomButtons, 1)
        toolbar.insert(self.zoomin_button, -1)

        self.zoomout_button = Gtk.ToolButton(Gtk.STOCK_ZOOM_OUT)
        self.zoomout_button.set_homogeneous(False)
        self.zoomout_button.set_tooltip_text('Zoom out')
        self.zoomout_button.connect('clicked', self.zoomButtons, -1)
        toolbar.insert(self.zoomout_button, -1)

        self.zoom_combo = Gtk.ComboBoxText()
        for zoom in self.zoom_levels:
            self.zoom_combo.append_text(str(zoom) + '%')
        self.zoom_combo.set_active(self.curr_zoom)
        self.zoom_combo.connect('changed', self.zoomComboBox)

        # place the combo box in a VButtonBox to prevent it from expanding vertically
        vbox = Gtk.VButtonBox()
        vbox.pack_start(self.zoom_combo, False, True, 0)
        t_item = Gtk.ToolItem()
        t_item.add(vbox)
        t_item.set_tooltip_text('Adjust the zoom level')
        t_item.set_expand(False)
        toolbar.insert(t_item, -1)

        toolbar.insert(Gtk.SeparatorToolItem(), -1)

        # build the y scale adjustment slider
        t_item = Gtk.ToolItem()
        t_item.add(Gtk.Label(label='Y:'))
        toolbar.insert(t_item, -1)

        self.vscale_adj = Gtk.Adjustment(0, 0, 0)
        # It appears that there is currently no Python-style constructor
        # available for Gtk.Scale(), so instead of the commented-out line
        # below, we have to explicitly use the C constructor.
        hslider = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=self.vscale_adj)
        #hslider = Gtk.Scale.new(Gtk.Orientation.HORIZONTAL, self.vscale_adj)
        hslider.set_draw_value(False)
        self.initYScaleSlider(self.selected_seqtv)

        #sizereq = hslider.size_request()
        #hslider.set_size_request(sizereq[0], 100)
        #hslider.set_size_request(60, sizereq[1])

        self.y_slider = Gtk.ToolItem()
        self.y_slider.add(hslider)
        self.y_slider.set_tooltip_text('Adjust the Y scale of the trace view')
        toolbar.insert(self.y_slider, -1)

        self.vscale_adj.connect('value_changed', self.yScaleChanged)

        toolbar.insert(Gtk.SeparatorToolItem(), -1)

        # build the toggle button for phred scores
        toggle = Gtk.CheckButton()
        toggle.set_label('conf. scores')
        toggle.set_active(True)
        toggle.connect('toggled', self.showConfToggled)

        # place the toggle button in a VButtonBox to prevent it from expanding vertically
        vbox = Gtk.VButtonBox()
        vbox.pack_start(toggle, False, True, 0)
        t_item = Gtk.ToolItem()
        t_item.add(vbox)
        t_item.set_tooltip_text('Turn the display of phred scores on or off')
        t_item.set_expand(False)
        toolbar.insert(t_item, -1)

        # if we got two sequences, build a combo box to choose between them
        if len(self.seqt_viewers) == 2:
            trace_combo = Gtk.ComboBoxText()

            # see if the forward trace is first or second
            if self.seqt_viewers[0].getSequenceTrace().isReverseComplemented():
                trace_combo.append_text('Reverse:')
                trace_combo.append_text('Forward:')
            else:
                trace_combo.append_text('Forward:')
                trace_combo.append_text('Reverse:')
            trace_combo.append_text('Both:')
            trace_combo.set_active(0)
            trace_combo.connect('changed', self.traceComboBox)

            # place the combo box in a VButtonBox to prevent it from expanding vertically
            vbox = Gtk.VButtonBox()
            vbox.pack_start(trace_combo, False)
            t_item = Gtk.ToolItem()
            t_item.add(vbox)
            #t_item.set_tooltip_text('Adjust the zoom level')
            toolbar.insert(t_item, 0)

            trace_combo.set_active(2)

        return toolbar
    
    def traceComboBox(self, trace_combo):
        self.selected_seqtv = trace_combo.get_active()

        if self.selected_seqtv == len(self.seqt_viewers):
            self.y_slider.set_sensitive(False)
        else:
            # set up the y-scale slider
            self.y_slider.set_sensitive(True)
            self.initYScaleSlider(self.selected_seqtv)

    def initYScaleSlider(self, viewer_index):
        curr_smax = self.seqt_viewers[viewer_index].getYScaleMax()
        smin = 100
        if curr_smax < smin:
            smin = curr_smax
        self.vscale_adj.set_lower(smin)
        self.vscale_adj.set_upper(self.start_yscalemax[viewer_index])
        self.vscale_adj.set_value(curr_smax)

    def yScaleChanged(self, adj):
        val = adj.get_value()
        self.seqt_viewers[self.selected_seqtv].setYScaleMax(val)

    def showConfToggled(self, toggle):
        if self.selected_seqtv == len(self.seqt_viewers):
            for viewer in self.seqt_viewers:
                viewer.setShowConfidence(toggle.get_active())
        else:
            self.seqt_viewers[self.selected_seqtv].setShowConfidence(toggle.get_active())

    def zoomButtons(self, button, increment):
        """
        Handles clicks on the "+"/"-" zoom buttons by translating them to changes
        of the zoom level combo box, which manages the actual zooming.
        """
        self.zoom_combo.set_active(self.curr_zoom + increment)

    def zoomComboBox(self, combobox):
        """
        Responds to changes of the zoom level combo box by enabling or disabling
        the "+"/"-" zoom buttons as appropriate and triggering the change in zoom
        level on the selected trace viewer(s).
        """
        self.curr_zoom = self.zoom_combo.get_active()

        # Check if we need to enable or disable any of the zoom buttons.
        if self.curr_zoom == (len(self.zoom_levels) - 1):
            self.zoomin_button.set_sensitive(False)
        elif not(self.zoomin_button.get_sensitive()):
            self.zoomin_button.set_sensitive(True)

        if self.curr_zoom == 0:
            self.zoomout_button.set_sensitive(False)
        elif not(self.zoomout_button.get_sensitive()):
            self.zoomout_button.set_sensitive(True)

        # If there are two trace viewers and their scrolling is synchronized,
        # unlock them before triggering the zoom.
        relock = self.scroll_locked
        if self.scroll_locked:
            self.unlockScrolling()

        # Zoom the trace viewer(s).
        if self.selected_seqtv == len(self.seqt_viewers):
            for viewer in self.seqt_viewers:
                viewer.zoom(self.zoom_levels[self.curr_zoom])
        else:
            self.seqt_viewers[self.selected_seqtv].zoom(self.zoom_levels[self.curr_zoom])

        # If scroll synchronization was initially enabled, relock the scrollbars.
        if relock:
            self.lockScrolling()

    def destroyed(self, widget):
        # Unregister this widget as an observer of the consensus sequence viewer.
        self.consv.getConsensusSequenceViewer().unregisterObserver('alignment_clicked', self.alignmentClicked)
