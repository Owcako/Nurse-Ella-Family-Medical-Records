import {createListCollection, Portal, Select} from '@chakra-ui/react'

// View: src/import/ui-flow.svg#U14
// Use one controlled accessible selector for language/member choices. The portal
// keeps options outside clipped panels; the hidden select preserves form/accessibility behavior.
export function Dropdown ({label, value, items, onChange, disabled = false, showLabel = false, className = '', menuClassName = '', action}: {
  label: string; value: string; items: {value: string; label: string}[]; onChange: (value: string) => void
  disabled?: boolean; showLabel?: boolean; className?: string; menuClassName?: string
  action?: {label: string; onClick: () => void}
})
{
  // An optional final action opens a dialog; it never becomes the selected
  // member or reaches the caller's filter/chat state.
  const actionValue = 'dropdown-action'
  const choices = action ? [...items, {value: actionValue, label: action.label}] : items
  const collection = createListCollection ({items: choices})
  return <Select.Root unstyled className={`dropdown ${className}`} collection={collection} value={[value]} disabled={disabled}
    positioning={{placement: 'bottom-start', sameWidth: true, gutter: 8}} onValueChange={details => {
      const next = details.value[0] ?? ''
      if (action && next === actionValue) action.onClick ()
      else onChange (next)
    }}>
    <Select.HiddenSelect />
    {showLabel && <Select.Label className="dropdown-label">{label}</Select.Label>}
    <Select.Control>
      <Select.Trigger className="dropdown-trigger" aria-label={label}>
        <Select.ValueText /><span className="dropdown-chevron" aria-hidden="true">⌄</span>
      </Select.Trigger>
    </Select.Control>
    <Portal><Select.Positioner className="dropdown-positioner">
      <Select.Content className={`dropdown-menu ${menuClassName}`} aria-label={label}>
        {choices.map (item => <Select.Item className={`dropdown-item${action && item.value === actionValue ? ' dropdown-action' : ''}`} item={item} key={item.value}>
          <Select.ItemText>{item.label}</Select.ItemText><Select.ItemIndicator className="dropdown-check">✓</Select.ItemIndicator>
        </Select.Item>)}
      </Select.Content>
    </Select.Positioner></Portal>
  </Select.Root>
}
