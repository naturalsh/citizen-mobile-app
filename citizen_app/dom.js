/* Makes page elements. Text from a pack (a name, a note, a notice) only ever becomes plain words here: nothing is
   read as HTML, so nothing that arrives from outside can turn into code. */

/* h('button', {class: 'big', type: 'button', onclick: go}, 'Go')
   class -> the element's classes, text -> its words, on... -> a listener, true -> an attribute without a value,
   null and false are left out (attributes and children alike). */
export function h(tag, attrs = {}, ...children) {
    const made = document.createElement(tag);
    for (const [name, value] of Object.entries(attrs)) {
        if (value == null || value === false) continue;
        if (name === 'style') throw new Error('no inline styles: the service forbids them for citizens');
        if (name === 'class') made.className = value;
        else if (name === 'text') made.textContent = value;
        else if (name.startsWith('on')) made.addEventListener(name.slice(2), value);
        else made.setAttribute(name, value === true ? '' : value);
    }
    made.append(...children.flat().filter(child => child != null && child !== false && child !== ''));
    return made;
}
