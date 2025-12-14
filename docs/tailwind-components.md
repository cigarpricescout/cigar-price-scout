# Cigar Price Scout - Tailwind + Alpine.js Component Library

This document provides reusable component patterns for maintaining consistency across all pages.

## Setup (Add to every HTML page)

```html
<head>
  <!-- Tailwind CSS -->
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            brand: {
              50: '#faf7f2',
              100: '#f5efe5',
              500: '#7c5c2e',
              600: '#6b4f27',
              700: '#5a4220',
            },
            ink: '#111111',
            muted: '#4b5563',
          },
          fontFamily: {
            serif: ['Cormorant Garamond', 'Georgia', 'serif'],
            display: ['Cinzel', 'Georgia', 'serif'],
          },
        },
      },
    }
  </script>
  
  <!-- Alpine.js -->
  <script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.x.x/dist/cdn.min.js"></script>
  
  <!-- Google Fonts -->
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700&family=Cormorant+Garamond:ital,wght@0,400;0,500;0,600;1,400;1,500&display=swap" rel="stylesheet" />
  
  <style>[x-cloak] { display: none !important; }</style>
</head>
```

---

## Layout Components

### Page Container
```html
<body class="bg-brand-50 font-serif text-ink text-lg leading-relaxed">
  <div class="max-w-6xl mx-auto px-5">
    <!-- Content here -->
  </div>
</body>
```

### Page Header
```html
<header class="flex flex-col items-center justify-center gap-2 py-7 text-center">
  <img src="/static/logo.png" alt="Cigar Price Scout Logo" class="w-24 h-20 object-contain" />
  <h1 class="font-display font-bold text-3xl tracking-wide">Cigar Price Scout</h1>
  <p class="italic text-muted text-xl mt-1">Tagline here</p>
</header>
```

### Page Title
```html
<h1 class="font-display font-bold text-3xl text-center tracking-wide mb-6">Page Title</h1>
```

### Section Title
```html
<h2 class="font-display font-bold text-2xl text-center tracking-wide mb-4">Section Title</h2>
```

### Footer
```html
<footer class="mt-10 py-5 border-t border-gray-200 text-center text-muted">
  <p class="space-x-2">
    <a href="/best-cigar-box-prices" class="text-brand-500 hover:underline">Best Cigar Box Prices</a>
    <span>|</span>
    <a href="/about.html" class="text-brand-500 hover:underline">About</a>
    <!-- ... more links -->
  </p>
  <p class="mt-2">&copy; 2025 Cigar Price Scout.</p>
</footer>
```

---

## Button Components

### Primary Button
```html
<button class="bg-brand-500 hover:bg-brand-600 text-white font-semibold py-3 px-6 rounded-lg transition-all duration-200 shadow-md hover:shadow-lg">
  Primary Action
</button>
```

### Primary Button (Full Width)
```html
<button class="w-full bg-brand-500 hover:bg-brand-600 text-white font-semibold py-4 px-6 rounded-xl transition-all duration-200 shadow-md hover:shadow-lg">
  Submit
</button>
```

### Danger Button
```html
<button class="bg-red-600 hover:bg-red-700 text-white font-semibold py-3 px-6 rounded-lg transition-all duration-200 shadow-md hover:shadow-lg">
  Delete
</button>
```

### Secondary Button
```html
<button class="bg-white hover:bg-gray-50 text-ink border border-gray-300 font-semibold py-3 px-6 rounded-lg transition-all duration-200">
  Cancel
</button>
```

### Link Button
```html
<a href="/page.html" class="inline-block bg-brand-500 hover:bg-brand-600 text-white py-3 px-6 rounded-lg font-semibold text-lg transition-all duration-200 shadow-md hover:shadow-lg hover:-translate-y-0.5">
  Link Button
</a>
```

### Disabled Button
```html
<button disabled class="bg-brand-500 text-white font-semibold py-3 px-6 rounded-lg opacity-50 cursor-not-allowed">
  Disabled
</button>
```

---

## Form Components

### Text Input
```html
<input type="text" 
       placeholder="Enter value..."
       class="w-full p-3 border border-gray-200 rounded-xl bg-white font-serif text-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400 transition-all" />
```

### Select Dropdown
```html
<select class="w-full p-3 border border-gray-200 rounded-xl bg-white font-serif text-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400 transition-all">
  <option value="">Select option...</option>
  <option value="1">Option 1</option>
</select>
```

### Disabled Select
```html
<select disabled class="w-full p-3 border border-gray-200 rounded-xl bg-gray-100 font-serif text-lg cursor-not-allowed">
  <option value="">Select option...</option>
</select>
```

### Textarea
```html
<textarea rows="4"
          placeholder="Enter text..."
          class="w-full p-3 border border-gray-200 rounded-xl bg-white font-serif text-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400 transition-all resize-none"></textarea>
```

### Checkbox
```html
<label class="flex items-center gap-2 cursor-pointer">
  <input type="checkbox" class="w-4 h-4 accent-brand-500 cursor-pointer" />
  <span class="font-medium">Checkbox label</span>
</label>
```

### Form Group (Label + Input)
```html
<div class="mb-4">
  <label class="block font-semibold mb-2">Label</label>
  <input type="text" class="w-full p-3 border border-gray-200 rounded-xl bg-white font-serif text-lg focus:outline-none focus:ring-2 focus:ring-brand-500/20 focus:border-brand-400 transition-all" />
</div>
```

### Required Field Indicator
```html
<label class="block font-semibold mb-2">
  Label <span class="text-red-500">*</span>
</label>
```

---

## Card Components

### Basic Card
```html
<div class="bg-white border border-gray-200 rounded-xl p-5 shadow-sm">
  <!-- Card content -->
</div>
```

### Card with Header
```html
<div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
  <div class="px-5 py-4 border-b border-gray-200 bg-gray-50">
    <h3 class="font-display font-semibold text-lg">Card Title</h3>
  </div>
  <div class="p-5">
    <!-- Card content -->
  </div>
</div>
```

---

## Alert Components

### Info Alert
```html
<div class="bg-sky-50 border border-sky-500 rounded-lg p-4 text-sky-700">
  <strong>Info:</strong> This is an informational message.
</div>
```

### Warning Alert
```html
<div class="bg-yellow-50 border border-yellow-200 rounded-lg p-4 text-yellow-800">
  <strong>Warning:</strong> This is a warning message.
</div>
```

### Success Alert
```html
<div class="bg-emerald-50 border border-emerald-500 rounded-lg p-4 text-emerald-700">
  <strong>Success:</strong> Operation completed successfully.
</div>
```

### Error Alert
```html
<div class="bg-red-50 border border-red-500 rounded-lg p-4 text-red-700">
  <strong>Error:</strong> Something went wrong.
</div>
```

---

## Table Components

### Styled Table
```html
<div class="overflow-x-auto">
  <table class="w-full border-collapse bg-white border border-gray-200 rounded-xl overflow-hidden shadow-sm">
    <thead>
      <tr class="bg-gray-50">
        <th class="p-3 border-b border-gray-200 text-left font-display font-semibold text-sm">Column 1</th>
        <th class="p-3 border-b border-gray-200 text-center font-display font-semibold text-sm">Column 2</th>
      </tr>
    </thead>
    <tbody>
      <tr class="hover:bg-gray-50 transition-colors">
        <td class="p-3 border-b border-gray-200">Value 1</td>
        <td class="p-3 border-b border-gray-200 text-center">Value 2</td>
      </tr>
    </tbody>
  </table>
</div>
```

---

## Badge Components

### Success Badge (Authorized Dealer)
```html
<span class="inline-block px-2 py-1 rounded text-xs font-semibold uppercase bg-emerald-100 text-emerald-700 border border-emerald-300">
  Authorized Dealer
</span>
```

### Warning Badge (Marketplace)
```html
<span class="inline-block px-2 py-1 rounded text-xs font-semibold uppercase bg-red-50 text-red-600 border border-red-200">
  Marketplace
</span>
```

### Info Badge
```html
<span class="inline-block px-3 py-1 rounded-lg bg-sky-100 text-sky-700 text-sm font-semibold">
  Info Badge
</span>
```

### Neutral Badge
```html
<span class="inline-block px-3 py-1 rounded-lg bg-gray-100 text-gray-700 text-sm font-semibold">
  Neutral Badge
</span>
```

### Chip (Filter)
```html
<span class="text-sm px-3 py-1.5 rounded-full border border-gray-200 bg-white text-gray-700">
  Filter: Value
</span>
```

---

## Modal Component (Alpine.js)

```html
<div x-data="{ open: false }">
  <button @click="open = true" class="bg-brand-500 text-white px-4 py-2 rounded-lg">
    Open Modal
  </button>
  
  <div x-show="open" x-cloak
       class="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-5"
       @click.self="open = false">
    <div class="bg-white rounded-xl p-6 max-w-lg w-full shadow-2xl">
      <h3 class="font-display font-bold text-xl mb-4">Modal Title</h3>
      <p class="text-muted mb-6">Modal content goes here.</p>
      <div class="flex gap-3 justify-end">
        <button @click="open = false" class="px-4 py-2 border border-gray-300 rounded-lg hover:bg-gray-50">
          Cancel
        </button>
        <button @click="open = false" class="bg-brand-500 text-white px-4 py-2 rounded-lg hover:bg-brand-600">
          Confirm
        </button>
      </div>
    </div>
  </div>
</div>
```

---

## Loading States

### Spinner
```html
<svg class="w-5 h-5 animate-spin text-brand-500" viewBox="0 0 24 24" fill="none" stroke="currentColor">
  <circle cx="12" cy="12" r="10" stroke-width="4" class="opacity-25"></circle>
  <path d="M4 12a8 8 0 018-8" stroke-width="4" class="opacity-75"></path>
</svg>
```

### Button with Loading State (Alpine.js)
```html
<button @click="loading = true" 
        :disabled="loading"
        class="flex items-center gap-2 bg-brand-500 text-white px-4 py-2 rounded-lg disabled:opacity-50">
  <svg x-show="loading" class="w-5 h-5 animate-spin" viewBox="0 0 24 24" fill="none" stroke="currentColor">
    <circle cx="12" cy="12" r="10" stroke-width="4" class="opacity-25"></circle>
    <path d="M4 12a8 8 0 018-8" stroke-width="4" class="opacity-75"></path>
  </svg>
  <span x-text="loading ? 'Loading...' : 'Submit'"></span>
</button>
```

---

## Responsive Utilities

### Hide on Mobile
```html
<div class="hidden md:block">Visible on tablet and desktop only</div>
```

### Hide on Desktop
```html
<div class="md:hidden">Visible on mobile only</div>
```

### Responsive Grid
```html
<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
  <!-- Grid items -->
</div>
```

---

## Color Reference

| Color | Class | Use |
|-------|-------|-----|
| Brand Primary | `bg-brand-500` / `text-brand-500` | Main accent, buttons, links |
| Brand Dark | `bg-brand-600` | Hover states |
| Background | `bg-brand-50` | Page background |
| Ink (Text) | `text-ink` | Primary text |
| Muted | `text-muted` | Secondary text |
| Success | `text-emerald-600` | Positive states, "Value" |
| Error | `text-red-600` | Errors, warnings |
| Info | `text-sky-700` | Informational |
| Premium | `text-blue-600` | Premium indicator |

---

## Quick Migration Checklist

When converting an existing page:

1. [ ] Add Tailwind CDN + config in `<head>`
2. [ ] Add Alpine.js CDN in `<head>`
3. [ ] Add Google Fonts links
4. [ ] Set body class: `bg-brand-50 font-serif text-ink text-lg leading-relaxed`
5. [ ] Wrap content in: `max-w-6xl mx-auto px-5`
6. [ ] Replace inline styles with Tailwind classes
7. [ ] Replace vanilla JS with Alpine.js `x-data`, `x-model`, `@click`, etc.
8. [ ] Update footer to match new design
9. [ ] Test responsive behavior
