/**
 * WCAG 2.4.1 bypass-blocks: let a keyboard or screen-reader user jump the
 * fixed header and land on the content.
 *
 * `sr-only` rather than `hidden` or `display:none` — the link has to stay in
 * the tab order and in the accessibility tree to be reachable at all. It is
 * clipped to a 1px box until focused, then un-clips and pins itself top-left.
 *
 * z-[60] is load-bearing, not decoration. SiteNav's header and the pipeline
 * ProgressBar both sit at z-50, so anything lower un-hides the link
 * *underneath* the blurred header — visible to a screen reader, invisible to
 * the sighted keyboard user who just tabbed to it.
 */
export default function SkipLink() {
  return (
    <a
      href="#content"
      className="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] btn-primary"
    >
      Skip to content
    </a>
  )
}
