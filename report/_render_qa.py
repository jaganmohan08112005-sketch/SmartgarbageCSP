import os, sys
sys.stdout = __import__('io').TextIOWrapper(sys.stdout.buffer, encoding='ascii', errors='replace')
import win32com.client
here = os.path.dirname(os.path.abspath(__file__))
deck = os.path.join(here, "DOCUMENT_FINAL.pptx")
out = os.path.join(here, "_deck_qa")
os.makedirs(out, exist_ok=True)
app = win32com.client.Dispatch("PowerPoint.Application")
pres = app.Presentations.Open(deck, WithWindow=False)
pres.SaveAs(out, 18)  # ppSaveAsJPG -> Slide1.JPG ...
pres.Close()
app.Quit()
print("rendered to", out)
