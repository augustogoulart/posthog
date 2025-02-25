describe('Person Visualization Check', () => {
    beforeEach(() => {
        cy.clickNavMenu('persons')
        cy.location('pathname').should('eq', '/persons')
        cy.get('.ant-spin-spinning').should('not.exist') // Wait until initial table load to be able to use the search
        cy.get('[data-attr=persons-search]').type('deb').should('have.value', 'deb')
        cy.get('.ant-input-search-button').click()
        cy.contains('deborah.fernandez@gmail.com').click()
    })

    it('Can access person page', () => {
        cy.get('[data-row-key="email"] > :nth-child(1)').should('contain', 'email')
    })

    it('Events table loads', () => {
        cy.get('.events').should('exist')
    })
})

describe('Person Show All Distinct Checks', () => {
    beforeEach(() => {
        cy.clickNavMenu('persons')
        cy.get('.ant-spin-spinning').should('not.exist') // Wait until initial table load
    })

    it('Should have no Show All Distinct Id Button', () => {
        cy.get('[data-attr=persons-search]').type('fernand{enter}')
        cy.get('.ant-radio-button-wrapper').contains('All users').click()
        cy.contains('deborah.fernandez@gmail.com').click()
        cy.get('[data-cy="show-more-distinct-id"]').should('not.exist')
    })
})
