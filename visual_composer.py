"""Compose exact reviewed copy over an illustration using local fonts. No AI."""
import base64
import io


def compose(illustration,brand,headline):
    from PIL import Image,ImageDraw,ImageOps
    from video import font,caption_lines
    if not isinstance(illustration,str) or not illustration.startswith('data:image/'):
        raise ValueError('Composition needs a saved local illustration')
    raw=base64.b64decode(illustration.split(',',1)[1],validate=True)
    if len(raw)>30_000_000:raise ValueError('Illustration exceeds local limit')
    if not isinstance(brand,str) or not 1<=len(brand)<=120 or not isinstance(headline,str) or not 1<=len(headline)<=450:
        raise ValueError('Provide a concise real brand and headline')
    canvas=Image.new('RGB',(1080,1080),'#171326');draw=ImageDraw.Draw(canvas)
    for size in (36,32,28,24,20):
        brand_face=font(size,True)
        if draw.textlength(brand,font=brand_face)<=952:break
    else:raise ValueError('Brand name does not fit; shorten its display label')
    draw.text((64,48),brand,font=brand_face,fill='#d7d0f6')
    for size in (64,56,48,40,32):
        face=font(size,True)
        try:lines=caption_lines(draw,headline,face,952)
        except ValueError:continue
        if len(lines)*(size+10)<=270:break
    else:raise ValueError('Headline does not fit without truncation')
    y=120
    for line in lines:draw.text((64,y),line,font=face,fill='#fffaff');y+=size+10
    with Image.open(io.BytesIO(raw)) as source:
        visual=ImageOps.fit(source.convert('RGB'),(952,570))
    mask=Image.new('L',visual.size);ImageDraw.Draw(mask).rounded_rectangle((0,0,951,569),radius=28,fill=255)
    canvas.paste(visual,(64,438),mask)
    output=io.BytesIO();canvas.save(output,'PNG')
    return 'data:image/png;base64,'+base64.b64encode(output.getvalue()).decode()
