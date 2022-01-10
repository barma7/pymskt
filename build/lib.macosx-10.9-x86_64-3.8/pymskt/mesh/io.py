import vtk
import os

def read_vtk(filepath):
    reader = vtk.vtkPolyDataReader()
    reader.SetFileName(filepath)
    reader.Update()
    return reader.GetOutput()


def write_vtk(mesh, filepath, scalar_name=None):
    # fileversion is the old legacy version because new tools (Slicer, Paraview) dont support vtk
    # version 5.1 which shipped with VTK 9. 
    # https://discourse.vtk.org/t/legacy-polydata-file-compatibility/5354
    # https://discourse.vtk.org/t/can-we-write-out-the-old-vtk-4-2-file-format-with-vtk-9/5066/17
    # https://gitlab.kitware.com/vtk/vtk/-/merge_requests/7652/diffs?commit_id=7f76b9e97b1a05cfe4fcd5f9af58f0d7a385b639#528e66f324b988666af9696641f935da71b6f670
    writer = vtk.vtkPolyDataWriter()
    writer.SetFileName(filepath)
    writer.SetInputData(mesh)
    if scalar_name is not None:
        writer.SetScalarsName(scalar_name)
    writer.Write()