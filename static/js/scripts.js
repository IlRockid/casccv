// Ancora CAS Management System Scripts

document.addEventListener('DOMContentLoaded', function() {
    // Initialize custom field counter
    let customFieldCount = 0;
    
    // Add custom field button handler
    const addCustomFieldBtn = document.getElementById('add-custom-field');
    if (addCustomFieldBtn) {
        addCustomFieldBtn.addEventListener('click', function() {
            addCustomField();
        });
    }
    
    // Gestione del submit del form per assicurarsi che le date siano nel formato corretto
    const guestForm = document.querySelector('form');
    if (guestForm) {
        guestForm.addEventListener('submit', function(e) {
            // Assicurati che le date siano nel formato corretto per l'invio
            document.querySelectorAll('input[type="date"]').forEach(input => {
                if (input.value && input.value.includes('/')) {
                    // Se la data è in formato italiano (DD/MM/YYYY), converte in YYYY-MM-DD per l'invio
                    const parts = input.value.split('/');
                    if (parts.length === 3) {
                        const day = parts[0];
                        const month = parts[1];
                        const year = parts[2];
                        
                        // Crea un input nascosto con il valore in formato YYYY-MM-DD
                        const hiddenInput = document.createElement('input');
                        hiddenInput.type = 'hidden';
                        hiddenInput.name = input.name;
                        hiddenInput.value = `${year}-${month}-${day}`;
                        guestForm.appendChild(hiddenInput);
                        
                        // Rinomina l'input originale per evitare conflitti
                        input.name = input.name + '_display';
                    }
                }
            });
        });
    }
    
    // Initialize DataTables
    const guestsTable = document.getElementById('guests-table');
    if (guestsTable) {
        // Check if DataTable is already initialized and destroy it
        if ($.fn.DataTable.isDataTable('#guests-table')) {
            $('#guests-table').DataTable().destroy();
        }
        
        $(guestsTable).DataTable({
            responsive: true,
            destroy: true,
            language: {
                search: "Cerca:",
                lengthMenu: "Mostra _MENU_ righe per pagina",
                info: "Visualizzazione da _START_ a _END_ di _TOTAL_ righe",
                infoEmpty: "Nessun risultato disponibile",
                infoFiltered: "(filtrato da _MAX_ righe totali)",
                zeroRecords: "Nessun risultato trovato",
                paginate: {
                    first: "Primo",
                    last: "Ultimo",
                    next: "Successivo",
                    previous: "Precedente"
                }
            }
        });
    }
    
    // Calculate fiscal code button handler
    const calculateCfBtn = document.getElementById('calculate-cf-btn');
    if (calculateCfBtn) {
        calculateCfBtn.addEventListener('click', function() {
            calculateFiscalCode();
        });
    }
    
    // Setup date display fields
    initializeDateFields();
    
    // Permit date change handler - auto calculate expiry
    const permitDateInput = document.getElementById('permit_date');
    if (permitDateInput) {
        permitDateInput.addEventListener('change', function() {
            calculatePermitExpiry();
        });
        
        // Aggiungi un altro listener per il caso in cui Flatpickr gestisca l'evento
        permitDateInput.addEventListener('input', function() {
            calculatePermitExpiry();
        });
    }
    
    // Listener aggiuntivo per catturare gli eventi dopo l'inizializzazione di Flatpickr
    document.addEventListener('DOMContentLoaded', function() {
        setTimeout(function() {
            // Aggiungi un messaggio informativo sotto al campo
            const permitDateDiv = document.querySelector('label[for="permit_date"]').closest('div.mb-3');
            const infoText = document.createElement('small');
            infoText.className = 'form-text text-muted';
            infoText.innerHTML = 'La data di scadenza verrà calcolata automaticamente (6 mesi dopo la data di rilascio)';
            permitDateDiv.appendChild(infoText);
            
            // Verifica se Flatpickr ha creato un input alternativo e aggiungi vari listener
            const flatpickrInput = document.querySelector('input.flatpickr-input[aria-labelledby="permit_date"]');
            if (flatpickrInput) {
                // Aggiungi diversi tipi di listener per catturare tutti gli eventi possibili
                ['change', 'input', 'blur', 'click'].forEach(function(eventType) {
                    flatpickrInput.addEventListener(eventType, function() {
                        setTimeout(function() {
                            calculatePermitExpiry();
                        }, 100);
                    });
                });
                
                // Aggiungi listener anche sull'input originale
                const originalInput = document.getElementById('permit_date');
                if (originalInput) {
                    ['change', 'input', 'blur'].forEach(function(eventType) {
                        originalInput.addEventListener(eventType, function() {
                            setTimeout(function() {
                                calculatePermitExpiry();
                            }, 100);
                        });
                    });
                }
            }
            
            // Se è in modalità modifica e c'è già una data di rilascio, calcola la scadenza
            const permitDateInput = document.getElementById('permit_date');
            if (permitDateInput && permitDateInput.value) {
                calculatePermitExpiry();
            }
            
            // Aggiungi un trigger manuale per il calcolo
            const permitDateLabel = document.querySelector('label[for="permit_date"]');
            if (permitDateLabel) {
                const calcButton = document.createElement('button');
                calcButton.type = 'button';
                calcButton.className = 'btn btn-sm btn-outline-primary ml-2';
                calcButton.innerHTML = '<i class="fas fa-calculator"></i> Calcola scadenza';
                calcButton.style.marginLeft = '10px';
                calcButton.addEventListener('click', function(e) {
                    e.preventDefault();
                    calculatePermitExpiry();
                });
                permitDateLabel.appendChild(calcButton);
            }
            
        }, 500); // Breve ritardo per assicurarsi che Flatpickr sia completamente inizializzato
    });
    
    // Family relation selection handler
    initializeFamilyRelationSelector();
    
    // Function to add a new custom field
    function addCustomField() {
        customFieldCount++;
        
        const customFieldsContainer = document.getElementById('custom-fields-container');
        if (!customFieldsContainer) return; // Exit if container not found
        
        const newRow = document.createElement('div');
        newRow.classList.add('row', 'custom-field-row');
        newRow.innerHTML = `
            <div class="col-md-5">
                <input type="text" class="form-control" name="custom_field_name_${customFieldCount}" placeholder="Nome campo">
            </div>
            <div class="col-md-5">
                <input type="text" class="form-control" name="custom_field_${customFieldCount}" placeholder="Valore">
            </div>
            <div class="col-md-2">
                <button type="button" class="btn btn-danger btn-remove-field" data-field-id="${customFieldCount}">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        `;
        
        customFieldsContainer.appendChild(newRow);
        
        // Add remove button handler
        const removeBtn = newRow.querySelector('.btn-remove-field');
        removeBtn.addEventListener('click', function() {
            removeCustomField(this);
        });
    }
    
    // Function to remove a custom field
    function removeCustomField(button) {
        const fieldId = button.getAttribute('data-field-id');
        const fieldRow = button.closest('.custom-field-row');
        fieldRow.remove();
    }
    
    // Funzione di utility per convertire una data da formato italiano a formato standard
    function parseItalianDate(dateStr) {
        // Verifica se la data è nel formato DD/MM/YYYY
        if (/^\d{2}\/\d{2}\/\d{4}$/.test(dateStr)) {
            const parts = dateStr.split('/');
            return new Date(parts[2], parts[1] - 1, parts[0]);
        }
        // Altrimenti usa il parsing standard
        return new Date(dateStr);
    }
    
    // Funzione di utility per formattare una data in formato italiano DD/MM/YYYY
    function formatItalianDate(date) {
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const year = date.getFullYear();
        return `${day}/${month}/${year}`;
    }
    
    // Function to calculate permit expiry date (6 months after issue date)
    function calculatePermitExpiry() {
        console.log("Calculating permit expiry date...");
        
        // Troviamo l'input della data di rilascio - può essere l'input originale o quello creato da Flatpickr
        const permitDateInput = document.getElementById('permit_date');
        const flatpickrDateInput = document.querySelector('.flatpickr-input[aria-labelledby="permit_date"]');
        const permitExpiryInput = document.getElementById('permit_expiry');
        const permitExpiryHidden = document.getElementById('permit_expiry_hidden');
        
        // Determina quale input usare
        const dateInput = flatpickrDateInput || permitDateInput;
        
        if (dateInput && permitExpiryInput) {
            // Ottieni il valore della data
            let dateValue = dateInput.value;
            console.log("Input date value:", dateValue);
            
            if (dateValue) {
                // Gestisce sia il formato YYYY-MM-DD che DD/MM/YYYY
                let permitDate;
                
                if (dateValue.includes('/')) {
                    // Se contiene /, è in formato italiano DD/MM/YYYY
                    permitDate = parseItalianDate(dateValue);
                } else {
                    // Altrimenti è nel formato standard YYYY-MM-DD
                    permitDate = new Date(dateValue);
                }
                
                // Verifica che la data sia valida
                if (isNaN(permitDate.getTime())) {
                    console.log("Invalid date:", dateValue);
                    return;
                }
                
                // Calcola la data di scadenza a 6 mesi dopo la data di rilascio
                const expiryDate = new Date(permitDate);
                expiryDate.setMonth(expiryDate.getMonth() + 6);
                
                // Formato italiano DD/MM/YYYY per l'input visibile
                const formattedItalianDate = formatItalianDate(expiryDate);
                permitExpiryInput.value = formattedItalianDate;
                
                // Formatta la data anche nel formato ISO per l'invio al server
                const year = expiryDate.getFullYear();
                const month = String(expiryDate.getMonth() + 1).padStart(2, '0');
                const day = String(expiryDate.getDate()).padStart(2, '0');
                const isoDate = `${year}-${month}-${day}`;
                
                // Aggiorna il campo nascosto per l'invio al server
                if (permitExpiryHidden) {
                    permitExpiryHidden.value = isoDate;
                }
                
                console.log("Permit expiry calculated: " + formattedItalianDate + " (ISO: " + isoDate + ")");
            } else {
                console.log("No date value found in the input");
                permitExpiryInput.value = '';
                if (permitExpiryHidden) {
                    permitExpiryHidden.value = '';
                }
            }
        } else {
            console.log("Required inputs not found:", {
                permitDateInput: Boolean(permitDateInput),
                flatpickrDateInput: Boolean(flatpickrDateInput),
                permitExpiryInput: Boolean(permitExpiryInput)
            });
        }
    }
    
    // Function to initialize family relation selector
    function initializeFamilyRelationSelector() {
        const familyRelationsContainer = document.getElementById('family-relations-container');
        const guestSelect = document.getElementById('related-guest');
        const relationSelect = document.getElementById('relation-type');
        const addRelationBtn = document.getElementById('add-relation-btn');
        
        if (addRelationBtn) {
            addRelationBtn.addEventListener('click', function() {
                const guestOption = guestSelect.options[guestSelect.selectedIndex];
                const relationOption = relationSelect.options[relationSelect.selectedIndex];
                
                if (guestOption.value && relationOption.value) {
                    const relation = relationOption.text + ' di ' + guestOption.text;
                    
                    // Add to textarea
                    const textarea = document.getElementById('family_relations');
                    if (textarea.value) {
                        textarea.value += '\n' + relation;
                    } else {
                        textarea.value = relation;
                    }
                }
            });
        }
    }
    
    // Initialize existing custom fields in edit mode
    const existingCustomFields = document.querySelectorAll('.existing-custom-field');
    if (existingCustomFields.length > 0) {
        existingCustomFields.forEach(function(field, index) {
            customFieldCount = Math.max(customFieldCount, index + 1);
            
            // Add remove button handler
            const removeBtn = field.querySelector('.btn-remove-field');
            if (removeBtn) {
                removeBtn.addEventListener('click', function() {
                    removeCustomField(this);
                });
            }
        });
    }
    
    // Date range validation for export form
    const exportForm = document.getElementById('export-form');
    if (exportForm) {
        exportForm.addEventListener('submit', function(event) {
            const dateFrom = document.getElementById('entry_date_from').value;
            const dateTo = document.getElementById('entry_date_to').value;
            
            if (dateFrom && dateTo) {
                if (new Date(dateFrom) > new Date(dateTo)) {
                    event.preventDefault();
                    alert('La data di inizio deve essere precedente alla data di fine.');
                }
            }
        });
    }
    
    // Mobile sidebar toggle is handled in layout.html - removed duplicate to fix double-click issue
    
    // Automatically close alerts after 5 seconds
    setTimeout(function() {
        const alerts = document.querySelectorAll('.alert');
        alerts.forEach(function(alert) {
            if (alert && typeof bootstrap !== 'undefined') {
                const bsAlert = new bootstrap.Alert(alert);
                bsAlert.close();
            }
        });
    }, 5000);
});

// Function to confirm delete
function confirmDelete(guestId, guestName) {
    if (confirm(`Sei sicuro di voler eliminare l'ospite ${guestName}?`)) {
        document.getElementById(`delete-form-${guestId}`).submit();
    }
}

// Function to calculate fiscal code (this will call the backend API)
function calculateFiscalCode() {
    const lastName = document.getElementById('last_name').value;
    const firstName = document.getElementById('first_name').value;
    const gender = document.getElementById('gender').value;
    const birthDateInput = document.getElementById('birth_date').value;
    const birthPlace = document.getElementById('birth_place').value;
    
    if (!lastName || !firstName || !gender || !birthDateInput || !birthPlace) {
        alert('Per calcolare il codice fiscale compilare: cognome, nome, sesso, data e luogo di nascita.');
        return;
    }
    
    // Normalizza il formato della data (potrebbe essere DD/MM/YYYY o YYYY-MM-DD)
    let birthDate = birthDateInput;
    if (birthDateInput.includes('/')) {
        // Converti da formato italiano DD/MM/YYYY a YYYY-MM-DD
        const parts = birthDateInput.split('/');
        if (parts.length === 3) {
            birthDate = `${parts[2]}-${parts[1]}-${parts[0]}`;
        }
    }
    
    // Update the date display field
    updateDateDisplay('birth_date');
    
    // Call backend API to calculate fiscal code
    fetch('/calculate_fiscal_code', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            last_name: lastName,
            first_name: firstName,
            gender: gender,
            birth_date: birthDate,
            birth_place: birthPlace
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.error) {
            alert('Errore: ' + data.error);
        } else {
            document.getElementById('fiscal_code').value = data.fiscal_code;
        }
    })
    .catch(error => {
        console.error('Error:', error);
        alert('Errore durante il calcolo del codice fiscale.');
    });
}

// Function to update the displayed date in dd/mm/yyyy format (Italian format)
// Versione semplificata che mantiene il formato corretto senza aggiungere elementi visivi
function updateDateDisplay(inputId) {
    const dateInput = document.getElementById(inputId);
    
    if (dateInput && dateInput.value) {
        // La gestione del formato della data avviene solo per il valore interno
        // ma non modifica quello che viene mostrato all'utente
        if (!dateInput.value.includes('/')) {
            // Se è nel formato standard YYYY-MM-DD, convertiamo per il formato interno
            const parts = dateInput.value.split('-');
            if (parts.length === 3) {
                const year = parts[0];
                const month = parts[1].padStart(2, '0');
                const day = parts[2].padStart(2, '0');
                
                // Salva il valore originale per l'invio del form
                dateInput.setAttribute('data-date', dateInput.value);
            }
        }
    }
}

// Function to initialize all date fields
function initializeDateFields() {
    // List of all date input fields
    const dateFields = ['birth_date', 'permit_date', 'permit_expiry', 'health_card_expiry', 'entry_date', 'check_in_date', 'check_out_date'];
    
    // Per ogni campo data, manteniamo solo il listener minimo necessario
    dateFields.forEach(fieldId => {
        const input = document.getElementById(fieldId);
        if (input) {
            // Impostiamo l'attributo placeholder
            input.placeholder = "gg/mm/aaaa";
            
            // Aggiorniamo il valore iniziale se necessario
            updateDateDisplay(fieldId);
            
            // Aggiungiamo un listener per il cambio
            input.addEventListener('change', function() {
                updateDateDisplay(fieldId);
            });
        }
    });
    
    // Non aggiungere messaggi di aiuto sui formati data - richiesto dal cliente
}
