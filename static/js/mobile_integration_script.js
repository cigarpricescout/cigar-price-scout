// mobile-integration.js - Convert desktop tables to mobile-friendly cards

function createMobileView() {
    // Only run on mobile devices
    if (window.innerWidth > 480) return;
    
    const priceTable = document.querySelector('.price-table');
    if (!priceTable) return;
    
    // Create mobile cards container
    const mobileContainer = document.createElement('div');
    mobileContainer.className = 'mobile-price-cards';
    
    // Get table headers for reference
    const headers = Array.from(priceTable.querySelectorAll('th')).map(th => th.textContent.trim());
    const rows = Array.from(priceTable.querySelectorAll('tbody tr'));
    
    // Convert each row to a mobile card
    rows.forEach((row, index) => {
        const cells = Array.from(row.querySelectorAll('td'));
        const card = createPriceCard(headers, cells, index === 0); // First card is best deal
        mobileContainer.appendChild(card);
    });
    
    // Replace table with mobile cards
    priceTable.style.display = 'none';
    priceTable.parentNode.insertBefore(mobileContainer, priceTable.nextSibling);
}

function createPriceCard(headers, cells, isBestDeal = false) {
    const card = document.createElement('div');
    card.className = `price-card ${isBestDeal ? 'best-deal' : ''}`;
    
    // Extract data from table cells (adjust indices based on your table structure)
    const retailerName = cells[0]?.textContent.trim() || 'Unknown Retailer';
    const dealerType = cells[1]?.textContent.trim() || '';
    const productDetails = cells[2]?.textContent.trim() || '';
    const basePrice = cells[3]?.textContent.trim() || '$0.00';
    const shipping = cells[4]?.textContent.trim() || '$0.00';
    const tax = cells[5]?.textContent.trim() || '$0.00';
    const total = cells[6]?.textContent.trim() || '$0.00';
    const status = cells[7]?.textContent.trim() || 'Unknown';
    const buyLink = cells[0]?.querySelector('a')?.href || '#';
    
    card.innerHTML = `
        <div class="price-card-header">
            <div class="retailer-name">${retailerName}</div>
            <div class="total-price">${total}</div>
        </div>
        
        <div class="price-breakdown">
            <div class="price-item">
                <span class="price-label">Base Price:</span>
                <span class="price-value">${basePrice}</span>
            </div>
            <div class="price-item">
                <span class="price-label">Shipping:</span>
                <span class="price-value">${shipping}</span>
            </div>
            <div class="price-item">
                <span class="price-label">Tax:</span>
                <span class="price-value">${tax}</span>
            </div>
            <div class="price-item">
                <span class="price-label">Status:</span>
                <span class="price-value stock-status ${status.toLowerCase().includes('stock') ? 'in-stock' : 'out-of-stock'}">${status}</span>
            </div>
        </div>
        
        ${dealerType ? `
        <div class="dealer-info">
            <div class="dealer-type">${dealerType}</div>
            ${dealerType.toLowerCase().includes('marketplace') ? 
                '<div class="dealer-warning">Buy at own risk</div>' : ''}
        </div>
        ` : ''}
        
        ${productDetails ? `
        <div class="product-info" style="font-size: 12px; color: #666; margin: 8px 0;">
            ${productDetails}
        </div>
        ` : ''}
        
        <a href="${buyLink}" class="buy-button" target="_blank" rel="noopener">
            View Deal at ${retailerName}
        </a>
    `;
    
    return card;
}

function fixSearchInputColor() {
    // Fix search input text color to black
    const searchInputs = document.querySelectorAll('input[type="search"], input[type="text"], .search-input');
    searchInputs.forEach(input => {
        input.style.color = '#000000';
    });
}

function addResponsiveMetaTag() {
    // Ensure viewport meta tag exists
    if (!document.querySelector('meta[name="viewport"]')) {
        const meta = document.createElement('meta');
        meta.name = 'viewport';
        meta.content = 'width=device-width, initial-scale=1.0, maximum-scale=5.0';
        document.head.appendChild(meta);
    }
}

function handleOrientationChange() {
    // Recreate mobile view on orientation change
    setTimeout(() => {
        const existingMobile = document.querySelector('.mobile-price-cards');
        if (existingMobile) {
            existingMobile.remove();
        }
        createMobileView();
    }, 100);
}

// Initialize mobile optimizations
function initMobileOptimizations() {
    addResponsiveMetaTag();
    fixSearchInputColor();
    createMobileView();
    
    // Handle window resize and orientation changes
    let resizeTimeout;
    window.addEventListener('resize', () => {
        clearTimeout(resizeTimeout);
        resizeTimeout = setTimeout(() => {
            fixSearchInputColor();
            
            // Remove existing mobile cards
            const existingMobile = document.querySelector('.mobile-price-cards');
            if (existingMobile) {
                existingMobile.remove();
            }
            
            // Recreate mobile view if needed
            createMobileView();
        }, 250);
    });
    
    // Handle orientation change on mobile devices
    window.addEventListener('orientationchange', handleOrientationChange);
}

// Run when DOM is loaded
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initMobileOptimizations);
} else {
    initMobileOptimizations();
}