import './index.css'

export interface SkeletonProps {
  width?: string
  height?: string
  rounded?: boolean
  className?: string
}

export default function Skeleton({
  width = '100%',
  height = '1rem',
  rounded = false,
  className = '',
}: SkeletonProps) {
  return (
    <div
      className={['skeleton', rounded ? 'skeleton--rounded' : '', className].filter(Boolean).join(' ')}
      style={{ width, height }}
      aria-hidden="true"
    />
  )
}
