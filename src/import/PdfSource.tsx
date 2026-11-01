import {Button} from '@chakra-ui/react'
import {useEffect, useRef, useState} from 'react'
import {Document, Page, pdfjs} from 'react-pdf'
import 'react-pdf/dist/Page/TextLayer.css'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import type {Labels} from './strings'
import {Loading} from '../Loading'

// ui-flow.svg#U9: render the preserved PDF in the app. Browser PDF plugins can
// leave an iframe blank; PDF.js provides the actual page pixels and controls.
pdfjs.GlobalWorkerOptions.workerSrc = new URL ('pdfjs-dist/build/pdf.worker.min.mjs', import.meta.url).toString ()
const options = {
  cMapUrl: '/pdfjs/cmaps/', cMapPacked: true,
  standardFontDataUrl: '/pdfjs/standard_fonts/', wasmUrl: '/pdfjs/wasm/',
}

// View: src/import/ui-flow.svg#U9
// Render preserved PDF pages with PDF.js and a selectable text layer. ResizeObserver
// tracks the viewer width; page/zoom controls remain independent from extracted saved text.
export default function PdfSource ({url, labels: t, zoom}: {url: string; labels: Labels; zoom: number})
{
  const holder = useRef<HTMLDivElement> (null)
  const [width, setWidth] = useState (320)
  const [pages, setPages] = useState (0)
  const [page, setPage] = useState (1)

  useEffect (() => {
    if (!holder.current) return
    const observer = new ResizeObserver (entries => setWidth (Math.floor (entries[0].contentRect.width)))
    observer.observe (holder.current)
    return () => observer.disconnect ()
  }, [])

  return <div className="pdf-source" ref={holder}>
    <div className="pdf-controls">
      <Button unstyled aria-label={t.previousPage} disabled={page <= 1} onClick={() => setPage (page - 1)}>←</Button>
      <span role="status">{t.page} {page} / {pages || '…'}</span>
      <Button unstyled aria-label={t.nextPage} disabled={page >= pages} onClick={() => setPage (page + 1)}>→</Button>
    </div>
    <div className="pdf-scroll">
      <Document file={url} options={options} onLoadSuccess={({numPages}) => setPages (numPages)}
        loading={<Loading center label={t.loadingPdf} />} error={<p role="alert" className="notice error">{t.pdfError}</p>}>
        <Page pageNumber={page} width={Math.max (160, Math.round (width * zoom / 100))}
          loading={<Loading center label={t.loadingPdf} />} error={<p role="alert" className="notice error">{t.pdfError}</p>} />
      </Document>
    </div>
  </div>
}
